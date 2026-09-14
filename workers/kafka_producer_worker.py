from PyQt6.QtCore import QThread, pyqtSignal

class KafkaProducerWorker(QThread):
    """
    Produces a list of pre-serialized messages to a Kafka topic.

    Serialization and encryption are done in the main thread before
    this worker is started, so the worker only handles network I/O.

    Signals
    -------
    delivery_report(idx, topic, partition, offset, error_str)
    producer_error(str)
    done(sent, failed)
    """

    delivery_report = pyqtSignal(int, str, int, int, str)
    producer_error  = pyqtSignal(str)
    done            = pyqtSignal(int, int)

    def __init__(
        self,
        broker:   str,
        topic:    str,
        messages: list,     # list of (key: bytes|None, value: bytes)
        tls_cfg:  dict | None,
    ):
        super().__init__()
        self.broker   = broker
        self.topic    = topic
        self.messages = messages
        self.tls_cfg  = tls_cfg

    def _build_conf(self) -> dict:
        conf = {
            "bootstrap.servers": self.broker,
            "acks":    "all",
            "retries": 0,
            "delivery.timeout.ms": 15000,
        }
        if self.tls_cfg:
            conf["security.protocol"] = "SSL"
            ca   = self.tls_cfg.get("ca_cert",    "").strip()
            cert = self.tls_cfg.get("client_cert","").strip()
            key  = self.tls_cfg.get("client_key", "").strip()
            pw   = self.tls_cfg.get("key_passphrase","").strip()
            if ca:   conf["ssl.ca.location"]           = ca
            if cert: conf["ssl.certificate.location"]  = cert
            if key:  conf["ssl.key.location"]          = key
            if pw:   conf["ssl.key.password"]          = pw
            if not self.tls_cfg.get("verify", True):
                conf["ssl.endpoint.identification.algorithm"] = "none"
        return conf

    def run(self):
        try:
            from confluent_kafka import Producer, KafkaException
        except ImportError:
            self.producer_error.emit(
                "confluent-kafka not installed — run: pip install confluent-kafka"
            )
            return

        try:
            producer = Producer(self._build_conf())
        except KafkaException as exc:
            self.producer_error.emit(f"producer init failed: {exc}")
            return

        sent   = 0
        failed = 0
        # Store results keyed by idx for ordered emit after flush
        results: dict[int, tuple] = {}

        def _cb(err, msg, idx):
            nonlocal sent, failed
            if err:
                failed += 1
                results[idx] = (msg.partition() if msg else -1, -1, str(err))
            else:
                sent += 1
                results[idx] = (msg.partition(), msg.offset(), "")

        try:
            for idx, (key, value) in enumerate(self.messages):
                producer.produce(
                    self.topic,
                    key=key,
                    value=value,
                    on_delivery=lambda err, msg, i=idx: _cb(err, msg, i),
                )
                producer.poll(0)   # trigger any queued callbacks immediately

            remaining = producer.flush(timeout=15)
            if remaining > 0:
                self.producer_error.emit(
                    f"{remaining} message(s) not acknowledged after 15 s flush"
                )
        except KafkaException as exc:
            self.producer_error.emit(f"kafka exception: {exc}")
        except Exception as exc:
            self.producer_error.emit(f"unexpected error: {exc}")

        for idx in sorted(results):
            partition, offset, error = results[idx]
            self.delivery_report.emit(idx, self.topic, partition, offset, error)

        self.done.emit(sent, failed)