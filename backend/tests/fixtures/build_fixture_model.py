"""Rebuild the tiny ONNX plumbing fixture.

RANDOM WEIGHTS. NO TRAINING. It exists only so the ONNX loading, inference and
class-restriction path can be tested. No accuracy claim can be made from it and
none is made anywhere in this repository.
"""
import json

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

LABELS = ["late_blight", "early_blight", "downy_mildew", "powdery_mildew",
          "purple_blotch", "turcicum_blight", "nitrogen_deficiency", "healthy"]

rng = np.random.default_rng(7)
W = rng.normal(0, 0.02, size=(3 * 64 * 64, len(LABELS))).astype(np.float32)
B = np.zeros((len(LABELS),), dtype=np.float32)

graph = helper.make_graph(
    [helper.make_node("Flatten", ["input"], ["flat"], axis=1),
     helper.make_node("MatMul", ["flat", "W"], ["mm"]),
     helper.make_node("Add", ["mm", "B"], ["logits"])],
    "tiny-plumbing-classifier",
    [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 64, 64])],
    [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, len(LABELS)])],
    initializer=[numpy_helper.from_array(W, "W"), numpy_helper.from_array(B, "B")])
model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
model.ir_version = 9
onnx.checker.check_model(model)
onnx.save(model, "tiny_vision.onnx")
json.dump({"labels": LABELS,
           "_note": "Plumbing fixture with random weights. Never a source of accuracy claims."},
          open("labels.json", "w"), indent=1)
print("built tiny_vision.onnx")
