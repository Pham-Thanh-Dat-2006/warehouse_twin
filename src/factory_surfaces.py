"""Measure conveyor working decks, excluding tall guards/scanner housings."""
CONTACT_GAP = .002


def support_height(belt, x, half_length=0.):
    spans = belt.get('surfaces', [(belt['x0'], belt.get('end', belt['x1']), belt['top'])])
    return max((z for left, right, z in spans
                if right >= x-half_length and left <= x+half_length), default=belt['top'])


def roller_bounds(prim):
    from pxr import Usd, UsdGeom
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    boxes = [cache.ComputeWorldBound(p).ComputeAlignedRange()
             for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies())
             if p.IsA(UsdGeom.Mesh) and '_roller' in p.GetName().lower()]
    if not boxes:
        raise ValueError('No roller geometry: ' + str(prim.GetPath()))
    return boxes


def roller_top(prim):
    heights = [b.GetMax()[2] for b in roller_bounds(prim)]
    if max(heights)-min(heights) > .01:
        raise ValueError('Expected a level conveyor: ' + str(prim.GetPath()))
    return sum(heights)/len(heights)


def translate_world(prim, offset):
    from pxr import UsdGeom, Gf
    cache = UsdGeom.XformCache()
    world = cache.GetLocalToWorldTransform(prim)
    world.SetTranslateOnly(world.ExtractTranslation()+Gf.Vec3d(*offset))
    local = world*cache.GetLocalToWorldTransform(prim.GetParent()).GetInverse()
    UsdGeom.Xformable(prim).MakeMatrixXform().Set(local)


def scanner_alignment(prim, top, y):
    boxes = roller_bounds(prim)
    center_y = sum((b.GetMin()[1]+b.GetMax()[1])/2 for b in boxes)/len(boxes)
    return [0., y-center_y, top-roller_top(prim)]


def measure_belt(stage, index):
    from pxr import Usd, UsdGeom
    row = index % 2
    root = (f'/Warehouse/Zones/Assembly/Line{row}/Conveyor' if index < 2
            else f'/Warehouse/Zones/Packing/Line{row}/Belt/Straight')
    x0, x1 = (7.,45.) if index < 2 else (55.5,94.5)
    y = (10.,23.,8.,21.)[index]
    top = roller_top(stage.GetPrimAtPath(root+'/Module0'))
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    parcel = cache.ComputeWorldBound(stage.GetPrimAtPath(root+'/Parcel0')).ComputeAlignedRange()
    result = {'id':index+1,'x0':x0,'x1':x1,'end':x1,'y':y,'top':top,
              'parcel_size':list(parcel.GetSize()),'surfaces':[[x0,x1,top]]}
    if index >= 2:
        parent = root.rsplit('/',1)[0]
        scanner = next((stage.GetPrimAtPath(parent+'/'+name)
                        for name in ('ScanningTransfer','InclinedTransfer')
                        if stage.GetPrimAtPath(parent+'/'+name)), None)
        if scanner is None:
            raise ValueError('Missing A61 scanning conveyor: '+parent)
        offset = scanner_alignment(scanner,top,y)
        bound = cache.ComputeWorldBound(scanner).ComputeAlignedRange()
        lo, hi = float(bound.GetMin()[0]), float(bound.GetMax()[0])
        result.update(end=hi,scanner={'path':str(scanner.GetPath()),'offset':offset,
                                     'x0':lo,'x1':hi,'top':top})
        result['surfaces'].append([lo,hi,top])
        # The scanner has a flat central belt a few millimeters above its
        # rollers. A carton crossing that insert rests on the highest support
        # under its footprint. A61 has no inclined outfeed.
        for p in Usd.PrimRange(scanner, Usd.TraverseInstanceProxies()):
            if p.IsA(UsdGeom.Mesh) and p.GetName().lower().endswith('_belt_01'):
                b = cache.ComputeWorldBound(p).ComputeAlignedRange()
                result['surfaces'].append([float(b.GetMin()[0]),float(b.GetMax()[0]),
                                           float(b.GetMax()[2])+offset[2]])
    return result
