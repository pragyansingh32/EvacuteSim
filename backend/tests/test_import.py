"""Plan import tests: image conversion, DXF conversion, and the API endpoint."""

from __future__ import annotations

import io

import pytest
from app.planimport import ImportParams, import_from_dxf, import_from_image


def make_plan_png(width=240, height=160, wall_gray=20, bg=245) -> bytes:
    """A tiny synthetic floor plan: dark walls on white, one inner wall."""
    from PIL import Image, ImageDraw

    img = Image.new("L", (width, height), bg)
    draw = ImageDraw.Draw(img)
    t = 4  # wall thickness in px
    draw.rectangle([0, 0, width - 1, height - 1], outline=wall_gray, width=t)
    # Inner vertical wall: a filled 5px bar (outline width is ignored for fills).
    draw.rectangle([width // 3 - 2, 0, width // 3 + 2, height // 2], fill=wall_gray)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class TestImageImport:
    def test_converts_walls_and_keeps_interior_floor(self):
        result = import_from_image(
            make_plan_png(), ImportParams(target_width=30, real_width_m=15.0), "Test plan"
        )
        draft = result.draft
        assert (draft.width, draft.height) == (30, 20)
        walls = set(draft.walls)
        assert len(walls) > 10
        # Border converted: top-left and bottom-right corners are walls.
        assert (0, 0) in walls and (29, 19) in walls
        # Interior of the plan is floor (not converted to wall).
        assert (5, 5) not in walls
        # The inner vertical wall (x = width/3 = 80px of 240 -> cell ~10).
        assert any(x in (9, 10, 11) and 2 <= y <= 9 for x, y in walls)
        # Cell size derives from real width / target cells.
        assert draft.cell_size_m == 0.5
        assert result.stats["source_type"] == "image"

    def test_invert_handles_light_on_dark(self):
        # White walls on dark background: without invert the whole grid looks
        # dark (dense-wall warning); with invert the border is detected.
        from PIL import Image, ImageDraw

        img = Image.new("L", (240, 160), 20)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 239, 159], outline=245, width=4)
        buf = io.BytesIO()
        img.save(buf, "PNG")

        dense = import_from_image(
            buf.getvalue(), ImportParams(target_width=30, real_width_m=15.0), "inv"
        )
        assert dense.stats["wall_ratio"] > 0.9
        assert any("too dense" in w for w in dense.warnings)

        result = import_from_image(
            buf.getvalue(),
            ImportParams(target_width=30, real_width_m=15.0, invert=True),
            "inv",
        )
        walls = set(result.draft.walls)
        assert (0, 0) in walls
        # Interior (dark background) is floor after inversion.
        assert (15, 10) not in walls
        assert result.stats["wall_ratio"] < 0.5

    def test_blank_image_rejected_with_clear_message(self):
        from PIL import Image

        img = Image.new("L", (200, 200), 255)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        with pytest.raises(ValueError, match="No walls were detected"):
            import_from_image(
                buf.getvalue(), ImportParams(target_width=30, real_width_m=15.0), "blank"
            )

    def test_invalid_params_rejected(self):
        with pytest.raises(ValueError, match="Target width"):
            import_from_image(
                make_plan_png(), ImportParams(target_width=4, real_width_m=15.0), "x"
            )
        with pytest.raises(ValueError, match="Real plan width"):
            import_from_image(
                make_plan_png(), ImportParams(target_width=30, real_width_m=0.5), "x"
            )

    def test_corrupt_image_rejected(self):
        with pytest.raises(ValueError, match="Could not decode"):
            import_from_image(
                b"not an image at all",
                ImportParams(target_width=30, real_width_m=15.0),
                "bad",
            )


MINIMAL_DXF = "\n".join(
    [
        "0", "SECTION", "2", "ENTITIES",
        # Rectangle of LINE entities
        "0", "LINE", "8", "WALLS", "10", "0.0", "20", "0.0", "11", "100.0", "21", "0.0",
        "0", "LINE", "8", "WALLS", "10", "100.0", "20", "0.0", "11", "100.0", "21", "60.0",
        "0", "LINE", "8", "WALLS", "10", "100.0", "20", "60.0", "11", "0.0", "21", "60.0",
        "0", "LINE", "8", "WALLS", "10", "0.0", "20", "60.0", "11", "0.0", "21", "0.0",
        # Inner dividing line
        "0", "LINE", "8", "WALLS", "10", "50.0", "20", "0.0", "11", "50.0", "21", "30.0",
        "0", "ENDSEC", "0", "EOF",
    ]
)


class TestDxfImport:
    def test_converts_lines_to_wall_cells(self):
        result = import_from_dxf(
            MINIMAL_DXF.encode(), ImportParams(target_width=50, real_width_m=25.0), "DXF plan"
        )
        draft = result.draft
        assert draft.width == 50
        walls = set(draft.walls)
        assert len(walls) > 50  # perimeter of a 50x30 grid
        # Border corners present.
        assert (0, 0) in walls and (49, 29) in walls
        # Inner divider around x=25, y<=15.
        assert any(x == 25 and y <= 15 for x, y in walls)
        # Interior floor exists.
        assert (10, 10) not in walls and (40, 20) not in walls
        assert result.stats["source_type"] == "dxf"
        assert result.stats["segments_imported"] == 5

    def test_dxf_without_geometry_rejected(self):
        empty = "0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1032\n0\nENDSEC\n0\nEOF\n"
        with pytest.raises(ValueError, match="No LINE"):
            import_from_dxf(
                empty.encode(), ImportParams(target_width=50, real_width_m=25.0), "empty"
            )

    def test_lwpolyline_closed_shape(self):
        dxf = "\n".join(
            [
                "0", "SECTION", "2", "ENTITIES",
                "0", "LWPOLYLINE", "90", "4", "70", "1",
                "10", "0.0", "20", "0.0",
                "10", "80.0", "20", "0.0",
                "10", "80.0", "20", "40.0",
                "10", "0.0", "20", "40.0",
                "0", "ENDSEC", "0", "EOF",
            ]
        )
        result = import_from_dxf(
            dxf.encode(), ImportParams(target_width=40, real_width_m=20.0), "poly"
        )
        walls = set(result.draft.walls)
        # Closed: all four corners are walls.
        assert (0, 0) in walls and (39, 19) in walls
        assert result.stats["segments_imported"] == 4


class TestImportEndpoint:
    def test_preview_converts_uploaded_png(self, client):
        resp = client.post(
            "/api/v1/import/preview",
            files={"file": ("plan.png", make_plan_png(), "image/png")},
            data={"name": "Uploaded office", "target_width": "30", "real_width_m": "15"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["draft"]["name"] == "Uploaded office"
        assert body["draft"]["width"] == 30
        # The synthetic plan's border has no openings: no auto exits possible,
        # and the system says so instead of inventing doors.
        assert body["draft"]["exits"] == []
        assert any("No opening to the outside" in w for w in body["warnings"])
        assert any("best-effort interpretation" in w for w in body["warnings"])
        assert len(body["draft"]["walls"]) > 10
        assert body["stats"]["source_type"] == "image"

    def test_preview_accepts_dxf(self, client):
        resp = client.post(
            "/api/v1/import/preview",
            files={"file": ("plan.dxf", MINIMAL_DXF.encode(), "application/dxf")},
            data={"target_width": "50", "real_width_m": "25"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["stats"]["source_type"] == "dxf"

    def test_unsupported_extension_rejected(self, client):
        resp = client.post(
            "/api/v1/import/preview",
            files={"file": ("plan.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        assert resp.status_code == 422
        assert "Unsupported file type" in resp.json()["error"]["message"]

    def test_empty_file_rejected(self, client):
        resp = client.post(
            "/api/v1/import/preview",
            files={"file": ("plan.png", b"", "image/png")},
        )
        assert resp.status_code == 422

    def test_conversion_failure_returns_clear_error(self, client):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("L", (200, 200), 255).save(buf, "PNG")
        resp = client.post(
            "/api/v1/import/preview",
            files={"file": ("blank.png", buf.getvalue(), "image/png")},
        )
        assert resp.status_code == 422
        assert "No walls were detected" in resp.json()["error"]["message"]
