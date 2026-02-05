import hashlib
import time


class ANVELChainValidator:
    def __init__(self):
        self.chain = []

    def add_block(self, data):
        timestamp = time.ctime()
        prev = self.chain[-1]["hash"] if self.chain else "GENESIS"
        block = prev + data + timestamp
        h = hashlib.sha256(block.encode()).hexdigest()
        self.chain.append({"data": data, "prev": prev, "hash": h, "time": timestamp})
        return f"[CHAIN] {h[:10]}"

    def validate_chain(self):
        for i in range(1, len(self.chain)):
            if self.chain[i]["prev"] != self.chain[i - 1]["hash"]:
                return f"[CHAIN] Invalid at {i}"
        return "[CHAIN] Valid"

    def tail(self, limit=5):
        return self.chain[-limit:] if self.chain else ["[CHAIN] No blocks"]
