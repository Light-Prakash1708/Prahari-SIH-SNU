"""
PRAHARI · object storage (S3 / Cloudflare R2) — verified against an in-process
S3 emulator (moto), because production photos move off the container disk the
moment STORAGE_PROVIDER=s3 is set, and that switch must not be the first time
the adapter runs.

What is pinned:
· an uploaded photograph is stored privately (no public grant) and read back
  byte-for-byte;
· the URL handed to the browser is a short-lived presigned GET, never a bare
  bucket URL;
· EXIF (which carries the GPS of a farmer's home) is gone before upload;
· the full scan path stores its image in the bucket when the app runs with
  STORAGE_PROVIDER=s3.

Skipped where moto is not installed, so CI does not gain a hard dependency.
"""
from __future__ import annotations

import io

import pytest

moto = pytest.importorskip("moto")


def _jpeg_with_gps_exif() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (320, 320), (40, 140, 60))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"           # Make
    exif[0x8825] = {1: "N", 2: (22.0, 53.0, 0.0)}   # GPSInfo: latitude
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


@pytest.fixture
def s3_env(env, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("S3_BUCKET", "prahari-test")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("S3_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_SECRET_KEY", "test")
    from moto import mock_aws
    with mock_aws():
        import boto3
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="prahari-test")
        from app.config import reload_settings
        yield reload_settings()


def test_s3_round_trip_is_private_and_presigned(s3_env):
    from app import storage
    st = storage.build_storage(s3_env)
    assert st.name == "s3"
    raw = _jpeg_with_gps_exif()
    clean = storage.sanitize(raw)
    key = st.put(storage.make_key("obs"), clean, "image/jpeg")
    assert st.get(key) == clean

    acl = st.client.get_object_acl(Bucket="prahari-test", Key=key)
    for g in acl["Grants"]:
        uri = (g.get("Grantee") or {}).get("URI", "")
        assert "AllUsers" not in uri and "AuthenticatedUsers" not in uri, "object must not be public"

    url = st.url(key)
    assert "X-Amz-Signature=" in url and "X-Amz-Expires=" in url
    assert st.health()["ok"] is True


def test_exif_and_gps_are_stripped_before_storage(s3_env):
    from PIL import Image

    from app import storage
    raw = _jpeg_with_gps_exif()
    with Image.open(io.BytesIO(raw)) as before:
        assert before.getexif().get(0x8825), "fixture must carry GPS EXIF"
    clean = storage.sanitize(raw)
    with Image.open(io.BytesIO(clean)) as after:
        ex = after.getexif()
        assert not ex.get(0x8825) and not ex.get(0x010F)


def test_a_scan_stores_its_photograph_in_the_bucket(s3_env):
    from fastapi.testclient import TestClient

    from app.main import create_app
    with TestClient(create_app(s3_env)) as c:
        r = c.post("/api/auth/register", json={
            "full_name": "Rajesh Pawar", "password": "strong-pass-2026",
            "phone": "9812345678", "taluka": "niphad"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        p = c.post("/api/plots", headers=h, json={
            "name": "T1", "crop": "tomato", "area_acre": 1.0, "sown_on": "2026-07-01",
            "lat": 20.08, "lng": 74.11, "location_source": "gps"}).json()
        from tests.conftest import leaf_image
        up = c.post("/api/observations", headers=h, data={"plot_id": p["id"]},
                    files={"image": ("leaf.jpg", leaf_image("blight"), "image/jpeg")})
        assert up.status_code == 201, up.text
        import boto3
        keys = [o["Key"] for o in boto3.client("s3", region_name="us-east-1")
                .list_objects_v2(Bucket="prahari-test").get("Contents", [])]
        assert keys, "the photograph never reached the bucket"
