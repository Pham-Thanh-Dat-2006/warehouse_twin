"""Share repeated prop geometry before RTX sees it; keep source USD unchanged."""
import argparse
import hashlib
import os
from pathlib import Path
from pxr import Sdf, Usd, UsdUtils


def shareable(prim):
    path = str(prim.GetPath())
    return (prim.GetName() == 'Model' and prim.GetParent().GetName() == 'UnitsAndAxes'
            and path.startswith('/Warehouse/') and '/Robots/' not in path
            and '/Crane/' not in path and '/Entrance/' not in path
            and not any(part.startswith('Arm') and part[3:].isdigit()
                        for part in path.split('/')))


def write_render_stage(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError('Render wrapper must not overwrite the source warehouse')
    original = Usd.Stage.Open(str(source))
    if not original or not original.GetPrimAtPath('/Warehouse/ROS2_robot1'):
        raise ValueError('Expected the ROS2 warehouse stage: ' + str(source))
    layer = Sdf.Layer.CreateAnonymous('warehouse_factory_runtime.usda')
    layer.subLayerPaths = [str(source)]
    library = Sdf.Layer.CreateAnonymous('warehouse_factory_props.usda')
    library_path = output.with_name(output.stem + '.props.usda')
    # Keep authored per-descendant changes (disabled rigid bodies, fan wheel
    # removal, etc.) inside the referenced definition. Merely making the old
    # Model instanceable would discard those descendant overrides in USD.
    definitions = UsdUtils.FlattenLayerStack(original)
    unique = {}
    references = []
    stage = Usd.Stage.Open(layer)
    for key in ('upAxis', 'metersPerUnit', 'timeCodesPerSecond', 'framesPerSecond',
                'startTimeCode', 'endTimeCode', 'defaultPrim', 'renderSettingsPrimPath'):
        if original.HasAuthoredMetadata(key):
            stage.SetMetadata(key, original.GetMetadata(key))
    paths = [p.GetPath() for p in original.Traverse() if shareable(p)]
    # Descendant joint frames of Comau arms stay editable. Prop placement and
    # collider siblings stay outside each shared Model root.
    for path in paths:
        candidate = Sdf.Layer.CreateAnonymous('prop.usda')
        if not Sdf.CopySpec(definitions, path, candidate, '/Prop'):
            raise RuntimeError('Cannot copy prop definition: ' + str(path))
        digest = hashlib.sha256(candidate.ExportToString().encode()).hexdigest()
        target = '/Props/P' + digest[:20]
        if digest not in unique:
            Sdf.CreatePrimInLayer(library, '/Props')
            if not Sdf.CopySpec(candidate, '/Prop', library, target):
                raise RuntimeError('Cannot share prop definition: ' + str(path))
            unique[digest] = target
        references.append((path, target))
    layer.customLayerData = {'warehouseRenderSource': str(source),
                             'sharedPropCount': len(paths), 'propDefinitions': len(unique)}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.stem + f'.{os.getpid()}.tmp.usda')
    temporary_library = library_path.with_name(library_path.stem + f'.{os.getpid()}.tmp.usda')
    try:
        if not library.Export(str(temporary_library)):
            raise RuntimeError('Failed to export shared prop definitions')
        temporary_library.replace(library_path)
        with Sdf.ChangeBlock():
            for path, target in references:
                prim = Sdf.CreatePrimInLayer(layer, path)
                prim.referenceList.explicitItems = [Sdf.Reference(str(library_path), target)]
                prim.instanceable = True
        if not layer.Export(str(temporary)):
            raise RuntimeError('Failed to export ' + str(temporary))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
        temporary_library.unlink(missing_ok=True)
    print(f'[FACTORY RENDER] {len(paths)} props share {len(unique)} definitions; original models, materials, '
          f'colliders and ROS graphs retained. Wrapper: {output}', flush=True)
    return output


if __name__ == '__main__':
    from project_paths import ROS2_USD, MAPS_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, default=ROS2_USD)
    parser.add_argument('--output', type=Path, default=MAPS_DIR/'warehouse_factory_runtime.usda')
    args = parser.parse_args()
    write_render_stage(args.stage, args.output)
