#!/usr/bin/env python3
"""Blender 5 background renderer: rotate + zoom a colored globe PLY.

Usage:
  blender --background --python scripts/render_globe_clip.py
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy


ROOT = Path("/Users/sankalp/Projects/20-inch-earth-globe")
PLY = ROOT / "docs/preview-video/globe_preview.ply"
FRAMES_DIR = ROOT / "docs/preview-video/frames"
OUT_BLEND = ROOT / "docs/preview-video/globe_clip.blend"

FPS = 24
DURATION_S = 10
WIDTH, HEIGHT = 1280, 720
RADIUS = 0.254  # meters after 0.001 scale from mm


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes) + list(bpy.data.materials) + list(bpy.data.lights) + list(bpy.data.cameras):
        bpy.data.batch_remove([block])


def import_globe():
    if hasattr(bpy.ops.wm, "ply_import"):
        bpy.ops.wm.ply_import(filepath=str(PLY))
    else:
        bpy.ops.import_mesh.ply(filepath=str(PLY))
    obj = bpy.context.selected_objects[0]
    obj.name = "Globe"
    # STL/PLY is in millimeters. Scale to meters so camera math is sane.
    obj.scale = (0.001, 0.001, 0.001)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # Generator is Z-up. Tilt slightly so the equator reads on camera.
    obj.rotation_euler = (math.radians(12.0), 0.0, 0.0)
    shade_smooth(obj)
    assign_vertex_color_material(obj)
    return obj


def shade_smooth(obj) -> None:
    mesh = obj.data
    if hasattr(mesh, "shade_smooth"):
        mesh.shade_smooth()
    else:
        bpy.ops.object.shade_smooth()
    if hasattr(mesh, "use_auto_smooth"):
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = math.radians(40)


def assign_vertex_color_material(obj) -> None:
    mat = bpy.data.materials.new("GlobeTerrain")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    attr = nodes.new("ShaderNodeVertexColor")
    color_layers = list(obj.data.color_attributes)
    if color_layers:
        attr.layer_name = color_layers[0].name
    bsdf.inputs["Roughness"].default_value = 0.42
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.22
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.22
    links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    obj.data.materials.append(mat)


def setup_world() -> None:
    world = bpy.data.worlds.new("Studio")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    bg = nodes.new("ShaderNodeBackground")
    out = nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Color"].default_value = (0.035, 0.038, 0.042, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_lights() -> None:
    def lamp(name, type_, loc, energy, size, color=(1, 1, 1)):
        data = bpy.data.lights.new(name, type_)
        data.energy = energy
        data.color = color
        if hasattr(data, "shadow_soft_size"):
            data.shadow_soft_size = size
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        bpy.context.scene.collection.objects.link(obj)
        return obj

    key = lamp("Key", "AREA", (0.9, -1.4, 0.7), 350, 0.4, (1.0, 0.97, 0.92))
    key.rotation_euler = (math.radians(65), 0, math.radians(20))
    if hasattr(key.data, "size"):
        key.data.size = 0.8
    lamp("Fill", "AREA", (-1.2, -0.6, 0.4), 80, 0.8, (0.75, 0.82, 0.95))
    lamp("Rim", "AREA", (0.2, 1.3, 0.5), 180, 0.3, (0.85, 0.9, 1.0))


def add_camera():
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50
    cam_data.clip_start = 0.01
    cam_data.clip_end = 20
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam

    target = bpy.data.objects.new("LookAt", None)
    bpy.context.scene.collection.objects.link(target)
    target.location = (0.0, 0.0, 0.0)
    constraint = cam.constraints.new(type="TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    return cam, target


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def animate(globe, cam, target) -> None:
    scene = bpy.context.scene
    total = FPS * DURATION_S
    scene.frame_start = 1
    scene.frame_end = total
    scene.render.fps = FPS

    # Start on the Atlantic / Americas, finish over the Himalaya after ~300°.
    start_z = math.radians(-70.0)
    end_z = math.radians(-70.0 + 305.0)

    # Camera looks at origin. Start wide enough to read the whole sphere,
    # then dolly in so the relief becomes tactile.
    wide = 1.85
    close = 0.72
    height = 0.22

    for frame in range(1, total + 1):
        t = (frame - 1) / (total - 1)
        rot = start_z + (end_z - start_z) * t
        globe.rotation_euler = (math.radians(12.0), 0.0, rot)
        globe.keyframe_insert("rotation_euler", frame=frame)

        # Hold wide for 4s, then ease in.
        zoom_t = ease_in_out(max(0.0, (t - 0.38) / 0.62))
        dist = wide + (close - wide) * zoom_t
        cam.location = (0.0, -dist, height * (1.0 - 0.15 * zoom_t))
        cam.keyframe_insert("location", frame=frame)
        # Bias the look-at toward the Himalaya as we zoom.
        target.location = (0.08 * zoom_t, 0.02 * zoom_t, 0.06 * zoom_t)
        target.keyframe_insert("location", frame=frame)


def configure_render() -> None:
    scene = bpy.context.scene
    # Blender 5.1 reports EEVEE Next as BLENDER_EEVEE.
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(FRAMES_DIR / "frame_")
    scene.render.film_transparent = False
    scene.render.use_motion_blur = False
    eevee = getattr(scene, "eevee", None)
    if eevee is not None:
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = 32
        if hasattr(eevee, "use_gtao"):
            eevee.use_gtao = True
        if hasattr(eevee, "use_bloom"):
            eevee.use_bloom = False
        if hasattr(eevee, "use_ssr"):
            eevee.use_ssr = True


def main() -> None:
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    clear_scene()
    setup_world()
    globe = import_globe()
    add_lights()
    cam, target = add_camera()
    animate(globe, cam, target)
    configure_render()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    bpy.ops.render.render(animation=True)
    print(f"rendered frames to {FRAMES_DIR}")


if __name__ == "__main__":
    main()
