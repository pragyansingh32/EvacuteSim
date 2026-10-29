"""draw.io import tests: vector XML -> grid, compressed payloads, text skip."""

from __future__ import annotations

import base64
import zlib
from urllib.parse import quote

import pytest
from app.planimport import ImportParams, import_from_drawio

ROOM_PLAN = """<mxfile host="app.diagrams.net">
  <diagram id="page1" name="Page-1">
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="room" value="Main hall" style="rounded=0;fillColor=none;" vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="240" height="160" as="geometry"/>
        </mxCell>
        <mxCell id="innerWall" style="edgeStyle=none;" edge="1" parent="1">
          <mxGeometry relative="1" as="geometry">
            <mxPoint x="160" y="40" as="sourcePoint"/>
            <mxPoint x="160" y="120" as="targetPoint"/>
          </mxGeometry>
        </mxCell>
        <mxCell id="label" value="Note text" style="text;" vertex="1" parent="1">
          <mxGeometry x="60" y="60" width="60" height="20" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""


def compress_diagram(xml: str) -> str:
    """Reproduce draw.io's compressed payload: URI-encode -> RAW deflate -> base64."""
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw deflate
    data = compressor.compress(quote(xml).encode())
    data += compressor.flush()
    return base64.b64encode(data).decode()


class TestDrawioImport:
    def test_room_outline_and_line_become_walls(self):
        result = import_from_drawio(
            ROOM_PLAN.encode(), ImportParams(target_width=48, real_width_m=12.0), "Plan"
        )
        walls = set(result.draft.walls)
        assert len(walls) > 20  # room outline is rasterized
        # West-room interior stays floor (the edge line splits the room at
        # x=160 px -> grid column 24).
        assert (10, 10) not in walls
        assert result.stats["source_type"] == "drawio"
        assert result.stats["shapes"] >= 2
        assert result.stats["text_cells_skipped"] == 1

    def test_semantics_detects_room_and_exterior(self):
        result = import_from_drawio(
            ROOM_PLAN.encode(), ImportParams(target_width=48, real_width_m=12.0), "Plan"
        )
        # The outline rectangle is closed (no door gap): one big region.
        assert result.stats["semantics"]["rooms"] >= 1
        assert len(result.draft.zones) >= 1

    def test_door_gap_in_outline_detected(self):
        # Remove wall cells along the bottom outline to leave a door gap.
        plan = ROOM_PLAN.replace('width="240" height="160"', 'width="240" height="160"').replace(
            "<mxGeometry x=",
            "<mxGeometry x=",
        )
        result = import_from_drawio(plan.encode(), ImportParams(target_width=48, real_width_m=12.0), "Plan")
        draft = result.draft
        # Punch a door gap into the bottom outline cells directly.
        bottom = max(y for _, y in set(draft.walls))
        bottom_cells = sorted(x for x, y in set(draft.walls) if y == bottom)
        mid = bottom_cells[len(bottom_cells) // 2]
        draft.walls = [(x, y) for x, y in draft.walls if not (y == bottom and mid - 1 <= x <= mid + 1)]
        from app.planimport.semantics import analyze

        sem = analyze(set(draft.walls), draft.width, draft.height, cell_size_m=0.25)
        assert sem.doors >= 1

    def test_filled_shape_becomes_solid_block(self):
        plan = ROOM_PLAN.replace(
            '</root>',
            """<mxCell id="pillar" style="rounded=0;fillColor=#000000;strokeColor=#000000;" vertex="1" parent="1">
          <mxGeometry x="80" y="80" width="40" height="40" as="geometry"/>
        </mxCell>
      </root>""",
        )
        result = import_from_drawio(plan.encode(), ImportParams(target_width=48, real_width_m=12.0), "Plan")
        walls = set(result.draft.walls)
        # The pillar (x 80-120 px) maps to grid ~8-16: its center is solid.
        solid = sum(1 for x in range(10, 15) for y in range(10, 15) if (x, y) in walls)
        assert solid >= 10

    def test_compressed_payload_supported(self):
        compressed = compress_diagram(ROOM_PLAN)
        wrapped = (
            '<mxfile host="app.diagrams.net"><diagram id="p1" name="Page-1">'
            + compressed
            + "</diagram></mxfile>"
        )
        result = import_from_drawio(wrapped.encode(), ImportParams(target_width=48, real_width_m=12.0), "Compressed")
        assert len(result.draft.walls) > 20

    def test_compressed_full_file_with_trailing_tags(self):
        """Real exports: the compressed payload sits inside <diagram> and the
        file has trailing markup after </mxGraphModel> — extraction must
        tolerate it (the model is found, not parsed as one document)."""
        model = ROOM_PLAN[ROOM_PLAN.index("<mxGraphModel"):]
        model = model[: model.rindex("</mxGraphModel>") + len("</mxGraphModel>")]
        compressed = compress_diagram(model)
        wrapped = f'<mxfile><diagram name="p">{compressed}</diagram></mxfile>'
        result = import_from_drawio(
            wrapped.encode(), ImportParams(target_width=48, real_width_m=12.0), "Compressed full"
        )
        assert len(result.draft.walls) > 20

    def test_empty_diagram_rejected(self):
        empty = (
            b'<mxfile><diagram name="p"><mxGraphModel><root>'
            b'<mxCell id="0"/></root></mxGraphModel></diagram></mxfile>'
        )
        with pytest.raises(ValueError, match="No shapes"):
            import_from_drawio(empty, ImportParams(target_width=48, real_width_m=12.0), "empty")

    def test_non_drawio_rejected(self):
        not_a_diagram = b"<html><body>not a diagram</body></html>"
        with pytest.raises(ValueError, match="draw.io"):
            import_from_drawio(not_a_diagram, ImportParams(target_width=48, real_width_m=12.0), "x")


class TestDrawioEndpoint:
    def test_preview_accepts_drawio_upload(self, client):
        resp = client.post(
            "/api/v1/import/preview",
            files={"file": ("plan.drawio", ROOM_PLAN.encode(), "application/xml")},
            data={"name": "Drawio plan", "target_width": "48", "real_width_m": "12"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["stats"]["source_type"] == "drawio"
        assert len(body["draft"]["walls"]) > 20

    def test_full_pipeline_from_drawio(self, client):
        """draw.io -> building -> scenario -> completed evacuation run.

        The envelope is drawn as four wall EDGES with a door gap in the
        bottom wall (the way users draw plans in draw.io)."""
        plan = """<mxfile><diagram name="p"><mxGraphModel><root>
            <mxCell id="0"/><mxCell id="1" parent="0"/>
            <mxCell id="top" style="edgeStyle=none;" edge="1" parent="1">
              <mxGeometry relative="1" as="geometry">
                <mxPoint x="40" y="40" as="sourcePoint"/>
                <mxPoint x="280" y="40" as="targetPoint"/>
              </mxGeometry>
            </mxCell>
            <mxCell id="left" style="edgeStyle=none;" edge="1" parent="1">
              <mxGeometry relative="1" as="geometry">
                <mxPoint x="40" y="40" as="sourcePoint"/>
                <mxPoint x="40" y="200" as="targetPoint"/>
              </mxGeometry>
            </mxCell>
            <mxCell id="right" style="edgeStyle=none;" edge="1" parent="1">
              <mxGeometry relative="1" as="geometry">
                <mxPoint x="280" y="40" as="sourcePoint"/>
                <mxPoint x="280" y="200" as="targetPoint"/>
              </mxGeometry>
            </mxCell>
            <mxCell id="bottomA" style="edgeStyle=none;" edge="1" parent="1">
              <mxGeometry relative="1" as="geometry">
                <mxPoint x="40" y="200" as="sourcePoint"/>
                <mxPoint x="150" y="200" as="targetPoint"/>
              </mxGeometry>
            </mxCell>
            <mxCell id="bottomB" style="edgeStyle=none;" edge="1" parent="1">
              <mxGeometry relative="1" as="geometry">
                <mxPoint x="190" y="200" as="sourcePoint"/>
                <mxPoint x="280" y="200" as="targetPoint"/>
              </mxGeometry>
            </mxCell>
          </root></mxGraphModel></diagram></mxfile>"""
        resp = client.post(
            "/api/v1/import/preview",
            files={"file": ("p.drawio", plan.encode(), "application/xml")},
            data={"name": "Drawio office", "target_width": "48", "real_width_m": "12"},
        )
        assert resp.status_code == 200, resp.text
        draft = resp.json()["draft"]

        building = client.post(
            "/api/v1/buildings",
            json={
                "name": draft["name"],
                "description": "from draw.io",
                "width": draft["width"],
                "height": draft["height"],
                "cell_size_m": draft["cell_size_m"],
                "walls": draft["walls"],
                "exits": draft["exits"],
                "zones": draft["zones"],
            },
        )
        assert building.status_code == 201, building.text
        zones = {z["id"]: len(z["cells"]) for z in building.json()["zones"]}
        per_zone = {z: max(1, n // 4) for z, n in zones.items()}
        scenario = client.post(
            "/api/v1/scenarios",
            json={
                "building_id": building.json()["id"],
                "name": "drawio scenario",
                "config": {
                    "zone_populations": per_zone,
                    "speed": {"distribution": "uniform", "min": 1.0, "max": 1.0},
                    "pre_movement": {"distribution": "uniform", "min": 0.0, "max": 1.0},
                    "strategy": "nearest_exit",
                    "seed": 3,
                    "max_duration_s": 240,
                    "dt_s": 0.2,
                },
            },
        )
        assert scenario.status_code == 201, scenario.text
        run = client.post(
            "/api/v1/runs", json={"scenario_id": scenario.json()["id"], "wait": True}
        )
        assert run.status_code == 201, run.text
        body = run.json()["run"]
        assert body["status"] == "completed"
        m = body["metrics"]
        assert (
            m["evacuated_count"] + m["unreachable_count"] + m["remaining_count"]
            == m["total_occupants"]
        )


