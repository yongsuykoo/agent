"""Reviewed Adobe DOM scripts. Only validated data is interpolated; no eval."""
import json
from .logo_design import validate_design

SERIALIZER = r'''
function quote(s) {
    return '"' + String(s).replace(/[\\"\x00-\x1f]/g, function(c) {
        if (c === '"') return '\\"';
        if (c === '\\') return '\\\\';
        return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
    }) + '"';
}
function encode(v) {
    if (v === null) return 'null';
    if (typeof v === 'string') return quote(v);
    if (typeof v === 'number' || typeof v === 'boolean') return String(v);
    var out = [], k;
    if (v instanceof Array) {
        for (k = 0; k < v.length; k++) out.push(encode(v[k]));
        return '[' + out.join(',') + ']';
    }
    for (k in v) if (v.hasOwnProperty(k)) out.push(quote(k) + ':' + encode(v[k]));
    return '{' + out.join(',') + '}';
}
'''

PROBE = '(function(){' + SERIALIZER + '''
var fonts = [];
for (var i = 0; i < app.fonts.length && i < 300; i++) fonts.push(app.fonts[i].postScriptName);
return encode({name: app.name, version: app.version, path: app.path.fsName, fonts: fonts});
})()'''

RENDER = r'''
var doc = null, units = app.preferences.rulerUnits, dialogs = app.displayDialogs;
function color(hex) { var c = new SolidColor(); c.rgb.hexValue = hex.slice(1); return c; }
function check() {
    if (File(payload.stop).exists) throw Error('Logo task cancelled.');
    if (doc && app.activeDocument != doc) throw Error('Active Photoshop document changed.');
}
try {
    check();
    app.preferences.rulerUnits = Units.PIXELS;
    app.displayDialogs = DialogModes.NO;
    var spec = payload.design;
    doc = app.documents.add(UnitValue(spec.width, 'px'), UnitValue(spec.height, 'px'),
        72, payload.name, NewDocumentMode.RGB, DocumentFill.TRANSPARENT, 1);
    doc.bitsPerChannel = BitsPerChannelType.EIGHT;
    doc.activeLayer.name = 'Agent base';
    if (spec.background !== null) {
        doc.selection.selectAll(); doc.selection.fill(color(spec.background)); doc.selection.deselect();
    }
    var i, j, points, layer, texts = [], bounds = [], fonts = [];
    for (i = 0; i < spec.shapes.length; i++) {
        check(); layer = doc.artLayers.add(); layer.name = 'Agent shape ' + (i+1);
        points = [];
        for (j = 0; j < spec.shapes[i].points.length; j++)
            points.push([spec.shapes[i].points[j][0]*spec.width, spec.shapes[i].points[j][1]*spec.height]);
        doc.selection.select(points); doc.selection.fill(color(spec.shapes[i].color)); doc.selection.deselect();
    }
    for (i = 0; i < spec.texts.length; i++) {
        check(); layer = doc.artLayers.add(); layer.name = 'Agent text ' + (i+1);
        layer.kind = LayerKind.TEXT;
        var t = spec.texts[i], item = layer.textItem;
        item.contents = t.text; item.font = t.font; item.size = UnitValue(t.size, 'px');
        item.color = color(t.color); item.position = [UnitValue(t.x*spec.width, 'px'), UnitValue(t.y*spec.height, 'px')];
        if (item.font !== t.font || item.contents !== t.text) throw Error('Photoshop substituted a font or text.');
        var b = layer.bounds, rectangle = [];
        for (j = 0; j < 4; j++) rectangle.push(b[j].as('px'));
        if (rectangle[0] < 0 || rectangle[1] < 0 || rectangle[2] > spec.width || rectangle[3] > spec.height || rectangle[2] <= rectangle[0] || rectangle[3] <= rectangle[1])
            throw Error('Text extends beyond the canvas or is invisible. Replan its size/position.');
        texts.push(item.contents); bounds.push(rectangle); fonts.push(item.font);
    }
    check();
    if (File(payload.psd).exists || File(payload.png).exists) throw Error('Task export already exists; refusing overwrite.');
    var psdOptions = new PhotoshopSaveOptions(); psdOptions.layers = true;
    doc.saveAs(File(payload.psd), psdOptions, false, Extension.LOWERCASE);
    check();
    var pngOptions = new PNGSaveOptions(); pngOptions.interlaced = false;
    doc.saveAs(File(payload.png), pngOptions, true, Extension.LOWERCASE);
    check(); var names = [];
    for (i = 0; i < doc.layers.length; i++) names.push(doc.layers[i].name);
    return encode({width: doc.width.as('px'), height: doc.height.as('px'),
        layers: names, texts: texts, fonts: fonts, text_bounds: bounds, document: doc.name});
} catch (error) {
    if (doc) { try { doc.close(SaveOptions.DONOTSAVECHANGES); } catch (ignored) {} }
    throw error;
} finally {
    app.preferences.rulerUnits = units;
    app.displayDialogs = dialogs;
}
'''


def render_script(design, directory, name, fonts):
    validate_design(design, '', fonts)
    payload = {'design': design, 'name': name, 'psd': str(directory/'logo.psd'),
               'png': str(directory/'logo.png'), 'stop': str(directory/'.cancel')}
    return '(function(){' + SERIALIZER + '\nvar payload = ' + json.dumps(payload, ensure_ascii=True, allow_nan=False) + ';\n' + RENDER + '})()'
