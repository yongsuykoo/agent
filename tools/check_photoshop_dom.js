// Execute the actual trusted ExtendScript against a simulated Adobe DOM.
// This validates script behavior, not native Photoshop or visual quality.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let checks = 0;
function exercise(script, options = {}) {
  const trace = [], existing = {name: 'User document', touched: false};
  let doc = null, stops = 0;
  const app = {name: 'Adobe Photoshop', version: '25.1', path: {fsName: 'C:\\Adobe'},
    fonts: [{postScriptName: 'ArialMT'}], preferences: {rulerUnits: 'inches'}, displayDialogs: 'normal',
    activeDocument: existing};
  function unit(value, units) { return {value, as: () => value}; }
  app.documents = {add: (w,h,res,name) => {
    doc = {name, width:w, height:h, layers:[{name:'initial'}]};
    doc.activeLayer = doc.layers[0];
    doc.selection = {selectAll: () => trace.push('selectAll'), deselect: () => {},
      select: points => trace.push(['polygon', points]), fill: c => trace.push(['fill', c.rgb.hexValue])};
    doc.artLayers = {add: () => {
      const layer = {name:'new', textItem:{}};
      Object.defineProperty(layer, 'bounds', {get: () => {
        const t = layer.textItem, x = t.position[0].value, y = t.position[1].value;
        const width = options.clipped ? 10000 : Math.min(20, t.contents.length);
        return [unit(x), unit(y-6), unit(x+width), unit(y)];
      }});
      doc.layers.unshift(layer); doc.activeLayer = layer; return layer;
    }};
    doc.saveAs = (file, settings, copy) => {
      if (options.saveError) throw Error('simulated export failure');
      trace.push(['save',file.path,copy]);
      if (options.changeDocument) app.activeDocument = existing;
    };
    doc.close = () => {trace.push('close-created');app.activeDocument=existing;};
    app.activeDocument = doc;
    return doc;
  }};
  const context = {app, UnitValue: unit, SolidColor: function(){this.rgb={};},
    PhotoshopSaveOptions: function(){}, PNGSaveOptions: function(){},
    File: path => ({path, exists: path.endsWith('.cancel') ? ++stops >= (options.cancelAt || Infinity) : !!options.exists}),
    Units:{PIXELS:'pixels'},DialogModes:{NO:'no'},NewDocumentMode:{RGB:'rgb'},
    DocumentFill:{TRANSPARENT:'transparent'},BitsPerChannelType:{EIGHT:8},
    LayerKind:{TEXT:'text'},Extension:{LOWERCASE:'lowercase'},SaveOptions:{DONOTSAVECHANGES:'discard'}};
  let result, error;
  try {result = JSON.parse(vm.runInNewContext(script,context,{timeout:3000}));}
  catch (e) {error = e;}
  assert.strictEqual(existing.touched,false);
  assert.strictEqual(app.preferences.rulerUnits,'inches');
  assert.strictEqual(app.displayDialogs,'normal');
  checks++;
  return {result,error,trace,doc,existing};
}
for (const item of cases) {
  const ok = exercise(item.script);
  assert.ifError(ok.error);
  assert.deepStrictEqual(ok.result.texts,item.texts);
  assert.strictEqual(ok.trace.filter(t=>Array.isArray(t)&&t[0]==='save').length,2);
  assert.strictEqual(ok.doc.layers.length,item.layers);
  assert(!ok.trace.includes('close-created'));
  for (const options of [{clipped:true},{saveError:true},{cancelAt:1},{cancelAt:3},{changeDocument:true},{exists:true}]) {
    const bad=exercise(item.script,options);
    assert(bad.error,JSON.stringify(options));
    if (bad.doc) assert(bad.trace.includes('close-created'));
  }
}
console.log(`Passed ${checks} trusted-script DOM scenarios (simulated Photoshop).`);
