import json
import threading
import queue

from PyQt6.QtCore import QThread, pyqtSignal

class KafkaConsumerWorker(QThread):
    """
    Polls a Kafka topic in a background thread and emits each message
    back to the UI via signals.

    Signals
    -------
    message_received(topic, partition, offset, timestamp_ms, decoded_str)
    status_update(str)   — informational progress line
    consumer_error(str)  — non-fatal or fatal error text
    done(int)            — emitted on exit with total messages consumed
    """

    message_received = pyqtSignal(str, int, int, int, int, str, bytes)
    #                              topic  part  off  ts_type  ts_ms  decoded  raw
    status_update    = pyqtSignal(str)
    consumer_error   = pyqtSignal(str)
    done             = pyqtSignal(int)

    # How many consecutive empty polls before giving up on 'latest' mode
    MAX_EMPTY_POLLS = 10

    def __init__(
        self,
        broker: str,
        topic: str,
        group_id: str,
        offset_mode: str,        # 'latest' | 'earliest' | 'specific'
        specific_offset: int,
        max_messages: int,
        tls_cfg: dict | None,
    ):
        super().__init__()
        self.broker          = broker
        self.topic           = topic
        self.group_id        = group_id
        self.offset_mode     = offset_mode
        self.specific_offset = specific_offset
        self.max_messages    = max_messages
        self.tls_cfg         = tls_cfg
        self._stop_flag      = threading.Event()
        self._err_queue      = queue.SimpleQueue()  # librdkafka error_cb → poll loop

    def stop(self):
        """Thread-safe stop — checked every poll cycle."""
        self._stop_flag.set()

    # ── build confluent_kafka config ─────────────────────────

    def _build_conf(self) -> dict:
        conf = {
            "bootstrap.servers":  self.broker,
            "group.id":           self.group_id,
            "auto.offset.reset":  "earliest" if self.offset_mode == "earliest" else "latest",
            "enable.auto.commit": False,
            "session.timeout.ms": 6000,
            "fetch.wait.max.ms":  500,
            "error_cb":           self._kafka_error_cb,
        }

        if self.tls_cfg:
            conf["security.protocol"] = "SSL"
            ca   = self.tls_cfg.get("ca_cert",   "").strip()
            cert = self.tls_cfg.get("client_cert","").strip()
            key  = self.tls_cfg.get("client_key", "").strip()
            pw   = self.tls_cfg.get("key_passphrase","").strip()
            if ca:
                conf["ssl.ca.location"] = ca
            if cert:
                conf["ssl.certificate.location"] = cert
            if key:
                conf["ssl.key.location"] = key
            if pw:
                conf["ssl.key.password"] = pw
            if not self.tls_cfg.get("verify", True):
                conf["ssl.endpoint.identification.algorithm"] = "none"
            # Request detailed SSL diagnostics from librdkafka
            conf["debug"] = "security,broker"

        return conf

    def _kafka_error_cb(self, err):
        """
        Called by librdkafka's internal thread on transport / auth / SSL errors.
        Cannot emit Qt signals directly from a foreign thread — use a queue
        that the poll loop drains each iteration instead.
        """
        self._err_queue.put(str(err))

    def _drain_errors(self):
        """Drain all pending librdkafka errors and emit them as signals."""
        while not self._err_queue.empty():
            try:
                self.consumer_error.emit(self._err_queue.get_nowait())
            except queue.Empty:
                break

    # ── main thread body ─────────────────────────────────────

    def run(self):
        try:
            from confluent_kafka import Consumer, TopicPartition, KafkaException, KafkaError
        except ImportError:
            self.consumer_error.emit(
                "confluent-kafka not installed — run: pip install confluent-kafka"
            )
            return

        conf = self._build_conf()
        self.status_update.emit(
            f"connecting  broker={self.broker}  topic={self.topic}  "
            f"group={self.group_id}  offset={self.offset_mode}"
        )

        try:
            consumer = Consumer(conf)
        except KafkaException as exc:
            self.consumer_error.emit(f"consumer init failed: {exc}")
            return

        received    = 0
        empty_polls = 0

        try:
            # ── offset assignment ────────────────────────────
            if self.offset_mode == "specific":
                try:
                    meta = consumer.list_topics(self.topic, timeout=10)
                except KafkaException as exc:
                    self._drain_errors()
                    self.consumer_error.emit(
                        f"failed to fetch topic metadata: {exc}"
                    )
                    return
                self._drain_errors()
                if self.topic not in meta.topics:
                    self.consumer_error.emit(f"topic '{self.topic}' not found on broker")
                    return
                t_meta = meta.topics[self.topic]
                if t_meta.error is not None:
                    self.consumer_error.emit(
                        f"topic metadata error: {t_meta.error}"
                    )
                    return
                partitions = [
                    TopicPartition(self.topic, pid, self.specific_offset)
                    for pid in t_meta.partitions
                ]
                consumer.assign(partitions)
                self.status_update.emit(
                    f"assigned {len(partitions)} partition(s) at offset {self.specific_offset}"
                )
            else:
                consumer.subscribe([self.topic])
                self.status_update.emit(f"subscribed — waiting for messages …")

            # ── poll loop ────────────────────────────────────
            while received < self.max_messages and not self._stop_flag.is_set():
                msg = consumer.poll(timeout=1.0)

                # Surface any async transport/SSL errors from librdkafka
                self._drain_errors()

                if msg is None:
                    empty_polls += 1
                    if empty_polls >= self.MAX_EMPTY_POLLS:
                        self.status_update.emit(
                            f"no messages after {self.MAX_EMPTY_POLLS} polls — stopping"
                        )
                        break
                    continue

                empty_polls = 0

                if msg.error():
                    from confluent_kafka import KafkaError
                    err_code = msg.error().code()
                    if err_code == KafkaError._PARTITION_EOF:
                        self.status_update.emit(
                            f"EOF  partition={msg.partition()}  offset={msg.offset()}"
                        )
                        if self.offset_mode in ("earliest", "specific"):
                            break
                        continue
                    if err_code == KafkaError._AUTHENTICATION:
                        self.consumer_error.emit(
                            f"authentication failed — check SASL/SSL credentials: {msg.error()}"
                        )
                        break
                    if err_code == KafkaError._SSL:
                        self.consumer_error.emit(
                            f"SSL error — check certificate paths and CA: {msg.error()}"
                        )
                        break
                    self.consumer_error.emit(
                        f"kafka error [{err_code}]: {msg.error()}"
                    )
                    break

                ts_type, ts_raw = msg.timestamp()
                # 0 = TIMESTAMP_NOT_AVAILABLE — value is undefined, treat as absent
                # 1 = TIMESTAMP_CREATE_TIME   — set by the producer
                # 2 = TIMESTAMP_LOG_APPEND_TIME — set by the broker on write
                ts_ms   = ts_raw if ts_type in (1, 2) and ts_raw > 0 else 0
                decoded = self._decode_value(msg.value())

                self.message_received.emit(
                    msg.topic(),
                    msg.partition(),
                    msg.offset(),
                    ts_type,
                    ts_ms,
                    decoded,
                    msg.value() or b"",
                )
                received += 1

        except KafkaException as exc:
            self.consumer_error.emit(f"kafka exception: {exc}")
        except Exception as exc:
            self.consumer_error.emit(f"unexpected error: {exc}")
        finally:
            self._drain_errors()   # catch any last errors before close
            consumer.close()
            self.done.emit(received)

    # ── value decoder ────────────────────────────────────────

    @staticmethod
    def _decode_value(raw: bytes | None) -> str:
        if raw is None:
            return "<null value>"

        # Confluent Avro wire format: 0x00 magic + 4-byte big-endian schema ID
        if len(raw) > 5 and raw[0] == 0x00:
            schema_id = int.from_bytes(raw[1:5], "big")
            payload   = raw[5:]
            try:
                parsed = json.loads(payload.decode("utf-8"))
                return (
                    f"[confluent-avro  schema_id={schema_id}]\n"
                    + json.dumps(parsed, indent=2, ensure_ascii=False)
                )
            except Exception:
                return (
                    f"[confluent-avro  schema_id={schema_id}  "
                    f"binary {len(payload)} bytes]\n{payload[:64].hex()}"
                )

        # Plain JSON
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # UTF-8 string
        try:
            return raw.decode("utf-8")
        except Exception:
            pass

        # Last resort: hex dump
        return f"<binary {len(raw)} bytes>  {raw[:64].hex()}"