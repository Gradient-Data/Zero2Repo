# feature: F17
"""Independent NumPy evaluation of the published BERT sentence-embedding model.

Model architecture and parameters come from the immutable public asset bundle.
The evaluator uses standard BERT attention, GELU, layer normalization, masked mean
pooling and unit normalization. It does not invoke or import the product.
"""
import hashlib
import json
import math
from pathlib import Path
import struct

ASSETS = Path(__file__).resolve().parent


def model_assets():
    declaration = json.loads((ASSETS / "F17_manifest.json").read_text())
    assert declaration["repository"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert declaration["revision"] == "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    for name, digest in declaration["sha256"].items():
        assert hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() == digest, name
    return ASSETS, declaration


def reference_embeddings(texts):
    import numpy as np
    from tokenizers import Tokenizer

    directory, _ = model_assets()
    config = json.loads((directory / "F17_config.json").read_text())
    tokenizer = Tokenizer.from_file(str(directory / "F17_tokenizer.json"))
    path = directory / "F17_model.safetensors"
    with path.open("rb") as stream:
        header_size = struct.unpack("<Q", stream.read(8))[0]
        header = json.loads(stream.read(header_size))
    weights = {}
    for name, entry in header.items():
        if name == "__metadata__" or entry["dtype"] != "F32":
            continue
        weights[name] = np.memmap(path, dtype="<f4", mode="r", offset=8+header_size+entry["data_offsets"][0],
                                  shape=tuple(entry["shape"])).astype(np.float64)

    def dense(x, prefix):
        return x @ weights[prefix+".weight"].T + weights[prefix+".bias"]

    def layer_norm(x, prefix):
        mean = x.mean(axis=-1, keepdims=True)
        variance = ((x-mean)**2).mean(axis=-1, keepdims=True)
        return ((x-mean) / np.sqrt(variance+config["layer_norm_eps"])) * weights[prefix+".weight"] + weights[prefix+".bias"]

    result = []
    heads = config["num_attention_heads"]
    width = config["hidden_size"] // heads
    erf = np.vectorize(math.erf, otypes=[float])
    for text in texts:
        encoded = tokenizer.encode(text)
        ids = np.asarray(encoded.ids)
        mask = np.asarray(encoded.attention_mask, dtype=np.float64)
        count = len(ids)
        x = (weights["embeddings.word_embeddings.weight"][ids]
             + weights["embeddings.position_embeddings.weight"][:count]
             + weights["embeddings.token_type_embeddings.weight"][0])
        x = layer_norm(x, "embeddings.LayerNorm")
        for layer in range(config["num_hidden_layers"]):
            prefix = f"encoder.layer.{layer}"
            q, k, v = (dense(x, prefix+".attention.self."+kind).reshape(count, heads, width).transpose(1, 0, 2)
                       for kind in ("query", "key", "value"))
            scores = q @ k.transpose(0, 2, 1) / math.sqrt(width)
            scores += (1-mask)[None, None, :] * -10000
            scores -= scores.max(axis=-1, keepdims=True)
            attention = np.exp(scores)
            attention /= attention.sum(axis=-1, keepdims=True)
            context = (attention @ v).transpose(1, 0, 2).reshape(count, -1)
            x = layer_norm(x+dense(context, prefix+".attention.output.dense"), prefix+".attention.output.LayerNorm")
            intermediate = dense(x, prefix+".intermediate.dense")
            activated = intermediate * 0.5 * (1+erf(intermediate/math.sqrt(2)))
            x = layer_norm(x+dense(activated, prefix+".output.dense"), prefix+".output.LayerNorm")
        pooled = (x*mask[:, None]).sum(axis=0)/mask.sum()
        result.append(pooled/np.linalg.norm(pooled))
    result = np.asarray(result)
    assert result.shape == (len(texts), 384)
    assert np.isfinite(result).all()
    return result, 0.0001
