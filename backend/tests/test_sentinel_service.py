"""Tests para el servicio Sentinel sin llamadas reales a CDSE."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from backend.services.sentinel import download_sentinel2


def _make_fake_image(height: int = 20, width: int = 20) -> np.ndarray:
    """Imagen sintética con valores de reflectancia realistas."""
    rng = np.random.default_rng(42)
    b04 = rng.uniform(0.02, 0.15, (height, width)).astype(np.float32)
    b08 = rng.uniform(0.30, 0.70, (height, width)).astype(np.float32)
    return np.stack([b04, b08], axis=-1)  # shape (H, W, 2)


def test_download_sentinel2_guarda_geotiff(tmp_path: Path) -> None:
    """Verifica que el GeoTIFF se escribe con las bandas y CRS correctos."""
    bbox = (-71.38, -34.652, -71.365, -34.64)
    output = tmp_path / "test_B04B08.tif"
    fake_image = _make_fake_image()

    with (
        patch("backend.services.sentinel.SentinelHubRequest") as mock_request,
        patch("backend.services.sentinel.bbox_to_dimensions", return_value=(20, 20)),
    ):
        instance = MagicMock()
        instance.get_data.return_value = [fake_image]
        mock_request.return_value = instance

        with patch.dict(
            "os.environ",
            {"SH_CLIENT_ID": "test-id", "SH_CLIENT_SECRET": "test-secret"},
        ):
            with patch("backend.services.sentinel.settings") as mock_settings:
                mock_settings.sh_client_id = "test-id"
                mock_settings.sh_client_secret = "test-secret"

                result = download_sentinel2(
                    bbox_coords=bbox,
                    date_from=date(2026, 3, 1),
                    date_to=date(2026, 3, 31),
                    output_path=output,
                )

    assert result == output
    assert output.exists()

    with rasterio.open(output) as ds:
        assert ds.count == 2
        assert ds.crs == CRS.from_epsg(4326)
        assert ds.width == 20
        assert ds.height == 20
        assert ds.nodata == -9999


def test_download_sentinel2_falla_sin_credenciales(tmp_path: Path) -> None:
    """Sin credenciales configuradas debe lanzar RuntimeError."""
    with patch("backend.services.sentinel.settings") as mock_settings:
        mock_settings.sh_client_id = ""
        mock_settings.sh_client_secret = ""

        with pytest.raises(RuntimeError, match="Credenciales"):
            download_sentinel2(
                bbox_coords=(-71.38, -34.652, -71.365, -34.64),
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
                output_path=tmp_path / "out.tif",
            )


def test_download_sentinel2_falla_sin_escenas(tmp_path: Path) -> None:
    """Si la API devuelve lista vacía debe lanzar ValueError."""
    with (
        patch("backend.services.sentinel.SentinelHubRequest") as mock_request,
        patch("backend.services.sentinel.bbox_to_dimensions", return_value=(20, 20)),
        patch("backend.services.sentinel.settings") as mock_settings,
    ):
        mock_settings.sh_client_id = "test-id"
        mock_settings.sh_client_secret = "test-secret"
        instance = MagicMock()
        instance.get_data.return_value = []
        mock_request.return_value = instance

        with pytest.raises(ValueError, match="Sin escenas"):
            download_sentinel2(
                bbox_coords=(-71.38, -34.652, -71.365, -34.64),
                date_from=date(2026, 1, 1),
                date_to=date(2026, 1, 2),
                output_path=tmp_path / "out.tif",
            )
