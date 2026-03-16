from hashlib import sha1

DISCOVERY_WINDOW_BARS = 24
DISCOVERY_STEP = 4
DISCOVERY_HORIZON = 8


def _window_signature(closes: list[float]) -> str:
    base = closes[0]
    normalized = [((value - base) / base) if base else 0.0 for value in closes]
    chunk_size = max(len(normalized) // 8, 1)
    compressed = [
        round(sum(normalized[index : index + chunk_size]) / len(normalized[index : index + chunk_size]), 4)
        for index in range(0, len(normalized), chunk_size)
    ]
    volatility_bucket = round((max(closes) - min(closes)) / max(closes[-1], 1e-9), 3)
    signature = "|".join(f"{value:.4f}" for value in compressed[:8]) + f"|{volatility_bucket:.3f}"
    return sha1(signature.encode("ascii")).hexdigest()


__all__ = ["DISCOVERY_HORIZON", "DISCOVERY_STEP", "DISCOVERY_WINDOW_BARS", "_window_signature"]
