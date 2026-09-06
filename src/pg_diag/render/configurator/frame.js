// Runs inside the vendored offline page, in the same module scope as `page`.
const reportSeed = JSON.parse(document.getElementById('pg-diag-configurator-context').textContent);
const applyReportTheme = theme => document.documentElement.setAttribute('data-pv-theme', theme === 'light' ? 'light' : 'dark');
applyReportTheme(reportSeed.theme);
window.addEventListener('message', event => {
  if (event.source === parent && event.data?.type === 'pg-diag-configurator-theme') {
    applyReportTheme(event.data.theme);
  }
});
const reportDefaults = {...page.values};
Object.assign(page.values, reportSeed.inputs);
page.diffText = reportSeed.currentConfig;
page.active = 'diff';
page.mount();
const reportCalculate = page.calculate.bind(page);
page.calculate = () => {
  reportCalculate();
  parent.postMessage({type: 'pg-diag-configurator-ready', error: page.error}, '*');
};

const provenance = document.createElement('details');
provenance.className = 'pc-report-inputs';
const heading = document.createElement('summary');
heading.textContent = `Inputs from report · ${reportSeed.settingCount} current settings · ${reportSeed.server}`;
provenance.append(heading);
for (const message of reportSeed.notes) {
  const note = document.createElement('p');
  note.textContent = message;
  provenance.append(note);
}
const sourceTable = document.createElement('table');
sourceTable.className = 'pc-table';
const headRow = document.createElement('tr');
for (const label of ['Input', 'Initial value', 'Source / assumption']) {
  const cell = document.createElement('th'); cell.textContent = label; headRow.append(cell);
}
const sourceHead = document.createElement('thead'); sourceHead.append(headRow); sourceTable.append(sourceHead);
const sourceBody = document.createElement('tbody');
for (const option of page.schema.options.filter(o => o.role === 'calculation')) {
  const source = reportSeed.sources.find(s => s.field === option.dest);
  const row = document.createElement('tr');
  const initial = formatInputValue(option.dest, page.values[option.dest]);
  for (const [column, value] of [option.dest, initial === null || initial === '' ? 'Automatic default' : initial,
    source ? `${source.confidence}: ${source.reason} [${source.itemIds.join(', ')}]` : 'Configurator default; not inferred from report measurements.'].entries()) {
    const cell = document.createElement('td');
    if (column === 1 && option.dest === 'available_extensions') {
      const extensions = String(value).split(',');
      extensions.forEach((extension, index) => {
        if (index > 0) cell.append(document.createElement('br'));
        cell.append(document.createTextNode(extension + (index < extensions.length - 1 ? ',' : '')));
      });
    } else {
      cell.textContent = String(value);
    }
    row.append(cell);
  }
  sourceBody.append(row);
}
sourceTable.append(sourceBody);
const sourceScroll = document.createElement('div'); sourceScroll.className = 'pc-tablewrap'; sourceScroll.append(sourceTable);
provenance.append(sourceScroll);
document.querySelector('.pc-tabrow').before(provenance);
// Keep the most consequential missing measurements visible even with details closed.
const caveat = reportSeed.notes.find(n => n.startsWith('Container filesystem'));
if (caveat) {
  const note = document.createElement('p'); note.className = 'pc-report-caveat'; note.textContent = caveat;
  provenance.before(note);
}
const resetToReport = () => {
  page.values = {...reportDefaults, ...reportSeed.inputs};
  page.sliderNodes = new Map(); page.profileChecks = null;
  page.buildForm(); page.calculate();
};
page.reset = resetToReport;
const resetButton = [...document.querySelectorAll('#actions button')].find(b => /reset/i.test(b.textContent));
if (resetButton) { resetButton.textContent = 'Reset to report inputs'; resetButton.title = 'Restore the inputs derived from this report'; }
const diffIntro = document.querySelector('#panel-diff .pc-table-intro');
if (diffIntro) diffIntro.textContent = 'Current pg_settings from this report are prefilled below, including parameters that the configurator does not tune. Differences compare running values and proposed values after unit conversion. Edit calculation inputs in Main.';
document.querySelector('#diff-input')?.setAttribute('aria-label', 'Current PostgreSQL settings from report');
// The parent accepts messages only from its own sandboxed iframe.
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') parent.postMessage({type: 'pg-diag-configurator-close'}, '*');
});
parent.postMessage({type: 'pg-diag-configurator-ready', error: page.error}, '*');
