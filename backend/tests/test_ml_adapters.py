"""
PRAHARI · dataset adapter properties
════════════════════════════════════════════════════════════════════════════
These tests do not need the datasets. They test the part of the pipeline that
is easy to get quietly wrong: the MAPPING from someone else's folder names to
PRAHARI's labels.

The failure they exist to prevent is specific. `Squash___Powdery_mildew` is
Podosphaera xanthii on squash. PRAHARI's `powdery_mildew` is Erysiphe necator
on grape. Merging them adds several hundred images to a class and makes every
metric look better, and the model that comes out has learned that squash
mildew is grape mildew. Nothing downstream can detect that — not the
validation split, not the confusion matrix, not a demo. Only this test can.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent.parent / "ml"
sys.path.insert(0, str(ML))


@pytest.fixture(scope="module")
def cd():
    from datasets import cropdisease
    return cropdisease


def test_every_label_the_adapter_can_emit_exists_in_problems_json(cd):
    from app import reference
    known = set(reference.DISEASES) | {"unknown"}
    for alias in cd.ALIASES:
        if alias["label"] is None:
            continue
        assert alias["label"] in known, \
            f"alias {alias['match']} emits '{alias['label']}', which no longer exists"
        assert alias["label"] in cd.LABELS, \
            f"'{alias['label']}' is missing from ml/labels.json"


def test_labels_json_matches_the_reference_data(cd):
    """The model's output order is a contract with the ONNX file. If someone
    adds a disease to problems.json and forgets labels.json, a deployed model
    starts returning the wrong class name for every prediction."""
    from app import reference
    assert set(cd.LABELS) == set(reference.DISEASES) | {"unknown"}


@pytest.mark.parametrize("folder,expected", [
    ("Tomato___Late_blight", "late_blight"),
    ("Corn_(maize)___Common_rust_", "common_rust_maize"),
    ("Corn___Northern_Leaf_Blight", "turcicum_blight"),
    ("Tomato___Tomato_Yellow_Leaf_Curl_Virus", "leaf_curl_tomato"),
    ("cotton_leaf_curl", "leaf_curl_cotton"),
    ("Cotton___bacterial_blight", "bacterial_blight_cotton"),
    ("Soybean___Yellow_mosaic", "yellow_mosaic_soybean"),
    ("Onion___Purple_blotch", "purple_blotch"),
    ("Pigeonpea___Fusarium_wilt", "fusarium_wilt_pigeonpea"),
    ("Grape___healthy", "healthy"),
])
def test_folder_names_resolve_to_the_right_label(cd, folder, expected):
    crop, tokens, _known = cd.tokenise(folder)
    alias = cd.resolve(crop, tokens)
    assert alias is not None, f"{folder} matched nothing"
    assert alias["label"] == expected


@pytest.mark.parametrize("folder,reason", [
    ("Squash___Powdery_mildew",
     "Podosphaera xanthii on squash is not Erysiphe necator on grape"),
    ("Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot",
     "maize grey leaf spot is not the soybean Cercospora PRAHARI models"),
    ("Tomato___Bacterial_spot",
     "Xanthomonas on tomato is not the cotton bacterial blight label"),
    ("Potato___Late_blight",
     "same pathogen, but PRAHARI has no potato reference set or thresholds"),
])
def test_the_adapter_refuses_to_cross_a_crop_boundary(cd, folder, reason):
    crop, tokens, _known = cd.tokenise(folder)
    alias = cd.resolve(crop, tokens)
    assert alias is None or alias["label"] is None, \
        f"{folder} was mapped to '{alias['label'] if alias else None}' — {reason}"


def test_an_unmodelled_crop_becomes_unknown_rather_than_being_discarded(cd, tmp_path):
    """A photograph of a potato leaf is not useless to a tomato model — it is
    exactly what teaches it to say 'unknown' instead of forcing every leaf it
    sees into a class it happens to have."""
    from PIL import Image
    for folder in ("Potato___healthy", "Tomato___Late_blight", "Zzz___mystery"):
        d = tmp_path / "ds" / folder
        d.mkdir(parents=True)
        for i in range(2):
            Image.new("RGB", (32, 32), (40, 120, 50)).save(d / f"{i}.jpg")
    records, report = cd.scan(tmp_path / "ds", unknown_from_unmapped=True)
    labels = {r["label"] for r in records}
    assert "unknown" in labels
    assert "late_blight" in labels
    # and the folder it could not read at all is REPORTED, not hidden
    assert any(u["class"] == "Zzz___mystery" for u in report["unmapped_classes"])


def test_the_manifest_does_not_claim_a_field_grouped_split_it_cannot_make(cd, tmp_path):
    """PlantDoc and the Kaggle sets carry no field identifier. The manifest has
    to say the grouping is weak, because an evaluation number read as
    field-grouped when it is filename-grouped is optimistic by a wide and
    unknowable margin."""
    fid = cd.field_id(Path("/x/Tomato___Late_blight/img_0042.jpg"), "Tomato___Late_blight")
    assert fid.startswith("kaggle:")
    src = (ML / "datasets" / "cropdisease.py").read_text()
    assert "field_grouping" in src and "WEAK" in src
