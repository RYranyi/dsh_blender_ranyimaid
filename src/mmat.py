"""mmat.py - material library (all procedural, no textures on disk)."""
import bpy
import mcore as C
import mprop as P


def get(name):
    return bpy.data.materials.get(name)


def _new(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type not in ("BSDF_PRINCIPLED", "OUTPUT_MATERIAL"):
            nt.nodes.remove(n)
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out is None:
        out = nt.nodes.new("ShaderNodeOutputMaterial")
    if not out.inputs["Surface"].is_linked:
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m, nt, bsdf


def _objco(nt):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    return tc.outputs["Object"]


def _dist(nt, co, center):
    n = nt.nodes.new("ShaderNodeVectorMath")
    n.operation = "DISTANCE"
    nt.links.new(co, n.inputs[0])
    n.inputs[1].default_value = center
    return n.outputs["Value"]


def _maprange(nt, val, a, b, c, d, smooth=True):
    n = nt.nodes.new("ShaderNodeMapRange")
    n.interpolation_type = "SMOOTHERSTEP" if smooth else "LINEAR"
    n.clamp = True
    n.inputs["From Min"].default_value = a
    n.inputs["From Max"].default_value = b
    n.inputs["To Min"].default_value = c
    n.inputs["To Max"].default_value = d
    nt.links.new(val, n.inputs["Value"])
    return n.outputs["Result"]


def _math(nt, op, a=None, b=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    if hasattr(a, "is_output"):
        nt.links.new(a, n.inputs[0])
    elif a is not None:
        n.inputs[0].default_value = a
    if hasattr(b, "is_output"):
        nt.links.new(b, n.inputs[1])
    elif b is not None:
        n.inputs[1].default_value = b
    return n.outputs[0]


def skin():
    if get("M_Skin"):
        return get("M_Skin")
    m, nt, b = _new("M_Skin")
    C._set(b, "Roughness", 0.42)
    C._set(b, "Specular IOR Level", 0.35)
    C._set(b, "Subsurface Weight", 0.20)
    C._set(b, "Subsurface Radius", (1.0, 0.40, 0.26))
    C._set(b, "Subsurface Scale", 0.010)
    C._set(b, "Coat Weight", 0.05)
    C._set(b, "Coat Roughness", 0.30)
    co = _objco(nt)
    d1 = _dist(nt, co, (0.094, -0.150, 0.6735))
    d2 = _dist(nt, co, (-0.094, -0.150, 0.6735))
    f1 = _maprange(nt, d1, 0.010, 0.056, 1.0, 0.0)
    f2 = _maprange(nt, d2, 0.010, 0.056, 1.0, 0.0)
    s = _math(nt, "MAXIMUM", f1, f2)
    # nose / lip warmth
    d3 = _dist(nt, co, (0.0, -0.150, 0.6500))
    f3 = _maprange(nt, d3, 0.008, 0.045, 0.45, 0.0)
    s2 = _math(nt, "ADD", s, f3, clamp=True)
    mix, out = C.mix_rgba(nt, s2, C.hexc(P.C_SKIN), C.hexc(P.C_BLUSH))
    nt.links.new(out, b.inputs["Base Color"])
    m.diffuse_color = C.hexc(P.C_SKIN)
    return m


def hair():
    if get("M_Hair"):
        return get("M_Hair")
    m, nt, b = _new("M_Hair")
    C._set(b, "Roughness", 0.36)
    C._set(b, "Specular IOR Level", 0.45)
    C._set(b, "Coat Weight", 0.32)
    C._set(b, "Coat Roughness", 0.16)
    C._set(b, "Anisotropic", 0.5)
    C._set(b, "Sheen Weight", 0.12)
    co = _objco(nt)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(co, sep.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "EASE"
    cr.elements[0].position = 0.55
    cr.elements[0].color = C.hexc(P.C_HAIR_DARK)
    cr.elements[1].position = 0.99
    cr.elements[1].color = C.hexc(P.C_HAIR_MID)
    e = cr.elements.new(0.72)
    e.color = C.hexc(P.C_HAIR_MID)
    e = cr.elements.new(0.87)
    e.color = C.hexc(P.C_HAIR_LIGHT)
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    m.diffuse_color = C.hexc(P.C_HAIR_MID)
    return m


def iris():
    """Iris: colour comes from the per-vertex 'Col' attribute (exact control)."""
    if get("M_Iris"):
        return get("M_Iris")
    m, nt, b = _new("M_Iris")
    ca = nt.nodes.new("ShaderNodeVertexColor")
    ca.layer_name = "Col"
    nt.links.new(ca.outputs["Color"], b.inputs["Base Color"])
    C._set(b, "Roughness", 0.46)
    C._set(b, "Coat Weight", 0.0)
    C._set(b, "Specular IOR Level", 0.35)
    m.diffuse_color = C.hexc(P.C_IRIS_MID)
    return m

def navy():
    if get("M_Navy"):
        return get("M_Navy")
    m, nt, b = _new("M_Navy")
    C._set(b, "Base Color", C.hexc(P.C_NAVY))
    C._set(b, "Roughness", 0.60)
    C._set(b, "Specular IOR Level", 0.32)
    C._set(b, "Sheen Weight", 0.35)
    C._set(b, "Sheen Roughness", 0.45)
    m.diffuse_color = C.hexc(P.C_NAVY)
    return m


def fabric_white(name="M_White", color=None, rough=0.55, sheen=0.4, coat=0.05):
    if get(name):
        return get(name)
    m, nt, b = _new(name)
    C._set(b, "Base Color", C.hexc(color or P.C_WHITE))
    C._set(b, "Roughness", rough)
    C._set(b, "Specular IOR Level", 0.30)
    C._set(b, "Sheen Weight", sheen)
    C._set(b, "Sheen Roughness", 0.42)
    C._set(b, "Coat Weight", coat)
    C._set(b, "Coat Roughness", 0.35)
    m.diffuse_color = C.hexc(color or P.C_WHITE)
    return m


def shoe():
    if get("M_Shoe"):
        return get("M_Shoe")
    m, nt, b = _new("M_Shoe")
    C._set(b, "Base Color", C.hexc(P.C_SHOE))
    C._set(b, "Roughness", 0.32)
    C._set(b, "Specular IOR Level", 0.55)
    C._set(b, "Coat Weight", 0.5)
    C._set(b, "Coat Roughness", 0.10)
    m.diffuse_color = C.hexc(P.C_SHOE)
    return m


def sole():
    if get("M_Sole"):
        return get("M_Sole")
    m, nt, b = _new("M_Sole")
    C._set(b, "Base Color", C.hexc(P.C_SHOE_DARK))
    C._set(b, "Roughness", 0.62)
    C._set(b, "Specular IOR Level", 0.3)
    m.diffuse_color = C.hexc(P.C_SHOE_DARK)
    return m


def flat(name, hexcolor, rough=0.5, metal=0.0, emit=0.0):
    if get(name):
        return get(name)
    m, nt, b = _new(name)
    c = C.hexc(hexcolor)
    C._set(b, "Base Color", c)
    C._set(b, "Roughness", rough)
    C._set(b, "Metallic", metal)
    C._set(b, "Specular IOR Level", 0.4)
    if emit:
        C._set(b, "Emission Color", c)
        C._set(b, "Emission Strength", emit)
    m.diffuse_color = c
    return m


def all_mats():
    return dict(
        skin=skin(), hair=hair(), navy=navy(),
        white=fabric_white(), shoe=shoe(), sole=sole(),
        iris=iris(),
        sclera=flat("M_Sclera", "#F8F5F7", rough=0.32),
        lash=flat("M_Lash", P.C_LASH, rough=0.38),
        brow=flat("M_Brow", P.C_EYEBROW, rough=0.5),
        red=flat("M_EyeRed", P.C_RED, rough=0.35),
        mouth=flat("M_Mouth", P.C_MOUTH, rough=0.45),
        highlight=flat("M_EyeLight", "#FFFFFF", rough=0.06, emit=0.4),
        irisline=flat("M_IrisLine", "#2C6A8E", rough=0.3),
        pearl=flat("M_Pearl", "#EFECE8", rough=0.16),
        sock=fabric_white("M_Sock", "#F3F0F1", rough=0.75, sheen=0.5),
        satin=fabric_white("M_Satin", "#FAF8F6", rough=0.26, sheen=0.6, coat=0.1),
        leather=shoe(),
    )
