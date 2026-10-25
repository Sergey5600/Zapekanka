# Zapekanka

Texture baking for game assets in Blender 4.2+. High to low poly baking with an automatic cage,
exploded bakes, supersampling, one-click PBR, engine presets, background baking and export to
Unreal Engine, Unity, Godot, Substance 3D Painter, Marmoset Toolbag, glTF and Roblox.

[Русская версия](README.ru.md)

## Features

- **High/low pairs.** Detected by name suffix (`Gun_low`, `Gun_high`, `Gun_high_bolt`, `Gun_cage`) or by
  collections (`Gun_low`, `Gun_high`). One button bakes the whole scene. Several pairs can share one
  texture set (atlas).
- **Automatic cage.** A temporary copy of the low poly pushed out along averaged normals, with uniform
  thickness on hard edges. Global or per-pair extrusion, live wireframe preview, "Estimate" measures the
  distance to the high poly. Ray distance is automatic (2x extrusion) or manual. Custom cage meshes work too.
- **Maps.** Normal (OpenGL / DirectX), Ambient Occlusion, Curvature, Thickness, Position, World Normal,
  Height, ID Color (per material, object, mesh island or vertex color).
- **One-click PBR.** Base Color, Roughness, Metallic, Normal, AO, Emission and Opacity from the high poly's
  materials. Materials are converted to emission copies (Principled and other BSDFs, node groups, linked
  inputs), so lighting never ends up in the textures. Cut-out transparency keeps clean colors.
- **Correct color spaces, always.** Base Color and Emission are written sRGB; Normal, Roughness, Metallic,
  AO, ORM and all mesh maps are Non-Color. Imported textures get the right color space automatically.
- **Packing.** ORM (R = AO, G = Roughness, B = Metallic) for Unreal, Godot and glTF; Unity metallic +
  smoothness; Unity HDRP mask map; opacity in Base Color alpha.
- **Exploded bake.** Pairs are moved apart while baking so their AO and rays do not interfere.
- **Supersampling** 2x / 4x / 8x with coverage-weighted downscaling (normals are re-normalized). Large bakes
  are split into tiles automatically, so 8K x 4x fits in memory.
- **Padding.** Seamless "Adjacent Faces" padding and a full-texture bleed (no seams in mip maps).
- **Pre-flight check** before every bake: unapplied or negative scale, missing UVs, overlapping or folded
  UVs, UV overlap between objects of one texture set, flipped normals, non-manifold edges, duplicate
  vertices, custom normals, non-triangulated low polys, missing or unsaved images. Fixes are one click away.
- **Engine presets**: Unreal Engine 5, Unity (URP / Built-in, HDRP), Godot 4, Roblox, glTF, Substance 3D
  Painter, Marmoset Toolbag. A preset sets the normal format, color spaces, naming (`T_Name_BC`,
  `T_Name_ORM` ...), packing and file format. Everything stays editable.
- **Non-destructive.** Baking happens in a private scene on duplicates. The user's objects, meshes,
  materials and render settings are never modified. Everything temporary is deleted, also after errors.
- **Background baking.** Bakes run in a separate `blender --background` process: the interface stays
  responsive at 8K, with progress, cancel and a job queue.
- **Automatic material.** After baking, a material with all textures connected (including the normal map
  with DirectX green flip, ORM channels, opacity and glTF occlusion) is created and assigned. Original
  materials can be restored.
- **Export.** Unreal Engine (live into a running editor, or a generated import script), Unity (FBX +
  textures + an editor script that sets up importers and materials), Godot (glb + `ORMMaterial3D`),
  Substance 3D Painter and Marmoset Toolbag (matching low/high/cage names), glTF / Sketchfab, Roblox.

## Installation

1. Download `zapekanka-<version>.zip` (Releases, or the `zapekanka-extension` artifact of the CI build).
2. Blender: **Edit > Preferences > Get Extensions > ⌄ > Install from Disk**, pick the zip.
3. The panel is in the 3D Viewport sidebar (**N**), tab **Zapekanka**.

Building the zip yourself: `python tools/build.py` (plain Python, no Blender needed).

## Quick start

1. Name your objects `Name_low` / `Name_high` (or put them into collections `Name_low` / `Name_high`).
   The low poly needs a UV map.
2. Pick a preset (for example *Unreal Engine 5*) and a map set (**Full PBR**, **Game**, **Mesh Maps**).
3. Set the output folder and resolution under **Output & Quality**. Save the .blend first if the folder is
   relative (`//textures/`).
4. **Detect Pairs**, then **Bake All**. Pre-flight runs first and stops the bake on errors.
5. Textures are written to the output folder, the material is assigned to the low poly. Use **Export** to
   send the asset to an engine.

### Pair naming

| Object name | Role |
|---|---|
| `Gun_low`, `Gun_lp`, `Gun_low.001` | low poly of pair `Gun` |
| `Gun_high`, `Gun_hp`, `Gun_high_bolt`, `Gun_high.002` | high polys of pair `Gun` |
| `Gun_cage` | optional custom cage (same topology as the low poly) |

Suffixes are configurable. A low poly without a high poly bakes its own materials (useful for
converting procedural materials to textures).

### Maps and color spaces

| Map | Color space | Notes |
|---|---|---|
| Base Color | sRGB | lighting-free, opacity can go to alpha |
| Emission | sRGB | skipped when completely black |
| Normal | Non-Color | OpenGL (Y+) or DirectX (Y-) |
| Roughness, Metallic, AO, ORM | Non-Color | ORM: R = AO, G = Roughness, B = Metallic |
| Opacity | Non-Color | skipped when fully opaque |
| Curvature | Non-Color | 0.5 = flat, brighter = convex |
| Thickness | Non-Color | white = thick |
| Height | Non-Color | 0.5 = low poly surface; the range is stored in `<set>.zapekanka.json` |
| Position | Non-Color | normalized to the bounds stored in `<set>.zapekanka.json` |
| World Normal | Non-Color | object-space normals |
| ID Color | Non-Color | stable colors per material / object / island |

Each bake writes `<texture set>.zapekanka.json` next to the textures. It lists the files, their channels
and color spaces and is used by **Import Texture Set** and the exporters.

### Presets

| Preset | Normals | Packing | Naming |
|---|---|---|---|
| Unreal Engine 5 | DirectX | ORM | `T_{name}_BC`, `T_{name}_N`, `T_{name}_ORM` |
| Unity URP / Built-in | OpenGL | Metallic (RGB) + Smoothness (A) | `{name}_Albedo`, `{name}_Normal`, `{name}_MetallicSmoothness` |
| Unity HDRP | OpenGL | Mask map (Metal, AO, -, Smooth) | `{name}_BaseColor`, `{name}_MaskMap` |
| Godot 4 | OpenGL | ORM | `{name}_albedo`, `{name}_orm` |
| glTF / Sketchfab | OpenGL | ORM | `{name}_baseColor`, `{name}_occlusionRoughnessMetallic` |
| Roblox | OpenGL | separate | `{name}_Color`, `{name}_Normal`, `{name}_Metalness`, `{name}_Roughness` |
| Substance 3D Painter | OpenGL, 16-bit | separate | `{name}_normal_base`, `{name}_ambient_occlusion`, ... |
| Marmoset Toolbag | OpenGL, 16-bit | separate | `{name}_normal`, `{name}_ao`, ... |

## Background baking

The default mode. The objects of the job are written to a small temporary .blend, a second Blender
(`blender --background --factory-startup`) bakes them and reports progress to the panel. Cancel stops the
process; further bakes are queued. Settings in **Preferences > Add-ons > Zapekanka**:

- *Blender Executable*: another Blender for baking (default: the running one).
- *Temporary Folder*, *Keep Job Files* (keeps the job folder with `worker.log`; failed jobs are always kept).
- *Low Priority Worker*, *Max Tile Size*.

The worker sees the **saved** state of images: pre-flight warns about unsaved images. Foreground mode bakes
inside the current session and blocks the interface.

GPU baking uses the devices enabled in **Preferences > System > Cycles Render Devices**.

## Export

Each target is written to its own subfolder of the export folder.

### Unreal Engine 5

Writes `SM_<set>.fbx`, the textures and `import_to_unreal.py`. The script imports the mesh (normals and
tangents from the FBX), imports the textures with the right compression and sRGB settings (normal map,
masks, color), builds `M_<set>` with all textures connected and assigns it.

**Send Live** sends the script to a running editor:

1. Enable the **Python Editor Script Plugin** in Unreal.
2. **Project Settings > Plugins > Python > Enable Remote Execution**.
3. Multicast group / port / bind address in the add-on preferences must match the Unreal settings
   (defaults: `239.0.0.1`, `6766`, `127.0.0.1`).

If no editor answers, the script stays in the export folder: **Tools > Execute Python Script** in Unreal.

### Unity

Set **Unity Project** to the project root to export straight into `Assets/<folder>/<set>/`. An editor
script (`Assets/Editor/Zapekanka/ZapekankaPostprocessor.cs`) configures texture importers (normal map
type, sRGB off for masks) and creates a URP, HDRP or Built-in material that is remapped onto the model.

### Godot 4

Set **Godot Project** to the folder with `project.godot`. Exports `<set>.glb` (the PBR material is embedded)
and `M_<set>.tres` (`ORMMaterial3D` or `StandardMaterial3D`) that uses the exported textures.

### Substance 3D Painter, Marmoset Toolbag

`<set>_low.fbx` and `<set>_high.fbx` with mesh names `<pair>_low` / `<pair>_high` (and `<pair>_cage` for
Marmoset), so both bakers match the groups automatically. Already baked maps are copied to `textures/`.
**Export and Open** starts the application set in the preferences.

### glTF / Sketchfab, Roblox

glTF: one self-contained `.glb` per texture set. Roblox: triangulated FBX in meters plus the textures and a
README with the SurfaceAppearance slots (Roblox accepts up to 1024 px).

## Troubleshooting

- **"N% of texels were not hit by rays"**: the cage does not enclose the high poly. Increase the extrusion
  (or use **Estimate**) or the ray distance. Missed texels are filled from their neighbours.
- **Seams on the normal map in the engine**: export the low poly triangulated (preset exporters do it) and
  bake with **Triangulate Low** if your engine triangulates differently.
- **Details from neighbouring parts in the AO**: enable **Exploded Bake** and put the parts into separate
  pairs.
- A background bake failed: **Open Log** shows the worker output.

## Development

```
pip install bpy==5.2.*         # or 4.2.* / 4.5.* with Python 3.11
python tests/run.py            # all tests (real Cycles bakes)
python tests/run.py test_core  # one module
python tools/build.py          # dist/zapekanka-<version>.zip
```

Layout:

- `zapekanka/core/`: bake engine, independent of the UI (runs in the add-on and in the worker).
- `zapekanka/worker.py`, `background.py`: background process and job queue.
- `zapekanka/exporters/`: export targets.
- `zapekanka/ui.py`, `props.py`, `operators/`: the add-on interface.
- `zapekanka/translations.py`: Russian interface.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
