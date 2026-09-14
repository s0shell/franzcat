import random
import datetime
import uuid
import string

class AvroRandomizer:
    """
    Recursively walks an Avro schema dict and produces a random
    Python value that is valid for that schema.

    Supported:
      Primitives  — null, boolean, int, long, float, double, bytes, string
      Complex     — record, array, map, enum, union, fixed
      Logical     — date, time-millis, time-micros, timestamp-millis,
                    timestamp-micros, uuid, decimal

    For unions the first non-null branch is preferred (mirrors how most
    application code treats nullable fields), but null is generated ~15 %
    of the time when the union contains it — useful for spotting nullable
    handling bugs on the consumer side.
    """

    ARRAY_LEN_RANGE  = (1, 4)
    MAP_KEYS_RANGE   = (1, 3)
    STRING_LEN_RANGE = (4, 24)
    BYTES_LEN_RANGE  = (4, 16)
    NULL_PROBABILITY = 0.15   # chance of emitting null in a nullable union

    def generate(self, schema: dict | str | list) -> object:
        """Entry point — pass the top-level parsed Avro schema."""
        return self._dispatch(schema)

    def _dispatch(self, schema) -> object:
        if isinstance(schema, str):
            return self._primitive(schema, logical_type=None)
        if isinstance(schema, list):
            return self._union(schema)
        if isinstance(schema, dict):
            logical_type = schema.get("logicalType") or schema.get("logical_type")
            avro_type    = schema.get("type")
            if isinstance(avro_type, str) and avro_type not in (
                "record", "array", "map", "enum", "fixed"
            ):
                return self._primitive(avro_type, logical_type)
            if avro_type == "record":
                return self._record(schema)
            if avro_type == "array":
                return self._array(schema)
            if avro_type == "map":
                return self._map(schema)
            if avro_type == "enum":
                return self._enum(schema)
            if avro_type == "fixed":
                return self._fixed(schema)
            if isinstance(avro_type, list):
                return self._union(avro_type)
        raise ValueError(f"Unsupported schema fragment: {schema!r}")

    def _record(self, schema: dict) -> dict:
        out = {}
        for field in schema.get("fields", []):
            out[field["name"]] = self._dispatch(field["type"])
        return out

    def _array(self, schema: dict) -> list:
        n = random.randint(*self.ARRAY_LEN_RANGE)
        return [self._dispatch(schema["items"]) for _ in range(n)]

    def _map(self, schema: dict) -> dict:
        n = random.randint(*self.MAP_KEYS_RANGE)
        return {
            self._rand_string(4, 10): self._dispatch(schema["values"])
            for _ in range(n)
        }

    def _enum(self, schema: dict) -> str:
        return random.choice(schema["symbols"])

    def _fixed(self, schema: dict) -> str:
        size = schema.get("size", 8)
        return bytes(random.getrandbits(8) for _ in range(size)).hex()

    def _union(self, types: list) -> object:
        non_null = [t for t in types if t != "null"]
        has_null = len(non_null) < len(types)
        if has_null and non_null and random.random() < self.NULL_PROBABILITY:
            return None
        if not non_null:
            return None
        return self._dispatch(random.choice(non_null))

    def _primitive(self, avro_type: str, logical_type: str | None) -> object:
        if logical_type == "uuid":
            return str(uuid.uuid4())
        if logical_type == "date":
            base  = datetime.date(1970, 1, 1)
            delta = datetime.timedelta(days=random.randint(0, 20_000))
            return (base + delta).isoformat()
        if logical_type == "time-millis":
            return random.randint(0, 86_400_000)
        if logical_type == "time-micros":
            return random.randint(0, 86_400_000_000)
        if logical_type == "timestamp-millis":
            return random.randint(946_684_800_000, 1_893_456_000_000)
        if logical_type == "timestamp-micros":
            return random.randint(946_684_800_000_000, 1_893_456_000_000_000)
        if logical_type == "decimal":
            return round(random.uniform(-1_000_000, 1_000_000), 6)

        if avro_type == "null":    return None
        if avro_type == "boolean": return random.choice([True, False])
        if avro_type == "int":     return random.randint(-(2**31), 2**31 - 1)
        if avro_type == "long":    return random.randint(-(2**63), 2**63 - 1)
        if avro_type == "float":   return round(random.uniform(-1e6,  1e6),  4)
        if avro_type == "double":  return round(random.uniform(-1e15, 1e15), 8)
        if avro_type == "string":
            return self._rand_string(*self.STRING_LEN_RANGE)
        if avro_type == "bytes":
            n = random.randint(*self.BYTES_LEN_RANGE)
            return bytes(random.getrandbits(8) for _ in range(n)).hex()
        return f"<unknown:{avro_type}>"

    @staticmethod
    def _rand_string(min_len: int, max_len: int) -> str:
        alphabet = string.ascii_letters + string.digits + "-_"
        return "".join(random.choices(alphabet, k=random.randint(min_len, max_len)))