from gravi.editor import RoomEditor, DEFAULT_CORE_RADIUS, DEFAULT_NODE_RADIUS
from gravi.field import Node
from gravi.room import Room


def make_room():
    return Room(spawn=(100.0, 100.0),
                nodes=[Node(300.0, 300.0, 240.0, 18.0)],
                width=1280.0, height=720.0)


def test_grab_selects_a_node_whose_core_contains_the_cursor():
    editor = RoomEditor(make_room())
    assert editor.grab(305.0, 302.0) is True
    assert editor.dragging is not None


def test_grab_misses_when_the_cursor_is_outside_every_core():
    editor = RoomEditor(make_room())
    assert editor.grab(800.0, 800.0) is False
    assert editor.dragging is None


def test_drag_moves_the_grabbed_node_and_release_stops_it():
    editor = RoomEditor(make_room())
    editor.grab(300.0, 300.0)
    editor.drag(500.0, 450.0)
    node = editor.room.nodes[0]
    assert (node.x, node.y) == (500.0, 450.0)
    editor.release()
    editor.drag(0.0, 0.0)
    assert (editor.room.nodes[0].x, editor.room.nodes[0].y) == (500.0, 450.0)


def test_add_node_appends_with_defaults():
    editor = RoomEditor(make_room())
    editor.add(700.0, 200.0)
    added = editor.room.nodes[-1]
    assert (added.x, added.y) == (700.0, 200.0)
    assert added.radius == DEFAULT_NODE_RADIUS
    assert added.core_radius == DEFAULT_CORE_RADIUS


def test_delete_removes_the_node_under_the_cursor():
    editor = RoomEditor(make_room())
    assert editor.delete(300.0, 300.0) is True
    assert editor.room.nodes == []


def test_delete_is_a_no_op_when_nothing_is_under_the_cursor():
    editor = RoomEditor(make_room())
    assert editor.delete(900.0, 100.0) is False
    assert len(editor.room.nodes) == 1


def test_hovered_uses_the_influence_radius_not_the_core():
    editor = RoomEditor(make_room())
    assert editor.hovered(420.0, 300.0) is editor.room.nodes[0]
    assert editor.hovered(1000.0, 300.0) is None


def test_resize_influence_radius_is_clamped():
    editor = RoomEditor(make_room())
    for _ in range(10_000):
        editor.resize_radius(300.0, 300.0, -1)
    assert editor.room.nodes[0].radius >= 40.0


def test_resize_core_radius_is_clamped_and_stays_below_influence():
    editor = RoomEditor(make_room())
    for _ in range(10_000):
        editor.resize_core(300.0, 300.0, +1)
    node = editor.room.nodes[0]
    assert node.core_radius <= node.radius * 0.5
