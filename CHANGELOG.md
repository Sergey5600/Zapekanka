# Changelog

## 1.0.0

First release.

- High/low pairs detected by name suffix (`_low` / `_high`, `_lp` / `_hp`, `_cage`) or by collections;
  several pairs can share one texture set (atlas).
- Automatic cage: averaged normals, uniform thickness on hard edges, per-pair extrusion, live wireframe
  preview, extrusion estimate. Custom cage meshes are supported.
- Maps: Normal (OpenGL / DirectX), Ambient Occlusion, Curvature, Thickness, Position, World Normal, Height,
  ID (material, object, mesh island, vertex color), Base Color, Roughness, Metallic, Emission, Opacity.
- PBR conversion from any node setup (Principled and other BSDFs, node groups, linked inputs, cut-out
  transparency) without lighting.
- Packing: ORM (Unreal, Godot, glTF), Unity metallic/smoothness, Unity HDRP mask map.
- Exploded bake, supersampling 2x/4x/8x with automatic tiling, seamless padding and full-texture bleed.
- Pre-flight check with one-click fixes.
- Engine presets: Unreal Engine 5, Unity URP/HDRP, Godot 4, Roblox, glTF, Substance 3D Painter, Marmoset.
- Background baking in a separate Blender process with progress, cancel and queue.
- Automatic material with all textures connected; texture set import.
- Export to Unreal (live via Python remote execution or import script), Unity (editor script creates
  materials), Godot (glb + ORMMaterial3D), Substance 3D Painter, Marmoset Toolbag, glTF/Sketchfab, Roblox.
- English and Russian interface.
