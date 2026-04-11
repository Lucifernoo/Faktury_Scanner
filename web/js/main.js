(function () {
  'use strict';

  let selectedPath = '';
  /** @type {'' | 'folder' | 'file'} */
  let selectedType = '';

  function appendLogLine(text) {
    const log = document.getElementById('log');
    if (!log) return;
    const line = document.createElement('div');
    line.textContent = text;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }

  function update_ui_status(state, filename) {
    const stamp = new Date().toLocaleTimeString();
    appendLogLine('[' + stamp + '] ' + state + ': ' + filename);
  }

  eel.expose(update_ui_status);

  function pluralZapysiv(n) {
    const nAbs = Math.abs(n) % 100;
    const n1 = n % 10;
    if (nAbs > 10 && nAbs < 20) {
      return 'записів';
    }
    if (n1 > 1 && n1 < 5) {
      return 'записи';
    }
    if (n1 === 1) {
      return 'запис';
    }
    return 'записів';
  }

  function on_registry_saved(count, savedPath) {
    const log = document.getElementById('log');
    if (!log) return;
    const line = document.createElement('div');
    line.className = 'log-registry';

    const iconWrap = document.createElement('span');
    iconWrap.className = 'log-registry__icon';
    iconWrap.setAttribute('aria-hidden', 'true');
    iconWrap.innerHTML =
      '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="20 6 9 17 4 12"></polyline></svg>';

    const text = document.createElement('span');
    text.className = 'log-registry__text';
    const n = parseInt(count, 10) || 0;
    text.textContent = savedPath
      ? 'Додано ' + n + ' ' + pluralZapysiv(n) + ': ' + savedPath
      : 'Додано ' + n + ' ' + pluralZapysiv(n) + ' до Реєстр_рахунків.xlsx';

    line.appendChild(iconWrap);
    line.appendChild(text);
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }

  eel.expose(on_registry_saved);

  function set_export_enabled(enabled) {
    const btn = document.getElementById('btn-excel');
    if (btn) {
      btn.disabled = !enabled;
    }
  }

  eel.expose(set_export_enabled);

  function update_progress(percent) {
    const fill = document.getElementById('progress-bar-fill');
    const strip = document.getElementById('progress-section');
    if (!fill || !strip) return;
    const v = Number(percent);
    if (v < 0 || Number.isNaN(v)) {
      strip.classList.remove('progress-section--active');
      fill.style.width = '0%';
      fill.setAttribute('aria-valuenow', '0');
      return;
    }
    strip.classList.add('progress-section--active');
    const w = Math.min(100, Math.max(0, v));
    fill.style.width = w + '%';
    fill.setAttribute('aria-valuenow', String(Math.round(w)));
  }

  eel.expose(update_progress);

  function expandLogCollapse() {
    const el = document.getElementById('log-collapse');
    if (!el || typeof bootstrap === 'undefined') return;
    if (el.classList.contains('show')) return;
    const inst = bootstrap.Collapse.getOrCreateInstance(el, { toggle: false });
    inst.show();
  }

  function refreshSelectionUI() {
    const pathEl = document.getElementById('selected-path-display');
    const startBtn = document.getElementById('start-btn');
    const labelEl = document.getElementById('start-btn-label');

    if (pathEl) {
      if (selectedPath) {
        pathEl.textContent = selectedPath;
        pathEl.classList.remove('is-empty');
      } else {
        pathEl.textContent = 'Нічого не обрано';
        pathEl.classList.add('is-empty');
      }
    }

    if (startBtn) {
      startBtn.disabled = !selectedPath;
    }

    if (labelEl) {
      if (!selectedPath) {
        labelEl.textContent = 'Обробити';
      } else if (selectedType === 'file') {
        labelEl.textContent = 'Обробити вибраний файл';
      } else if (selectedType === 'folder') {
        labelEl.textContent = 'Почати обробку папки';
      } else {
        labelEl.textContent = 'Обробити';
      }
    }
  }

  async function onSelectFolder() {
    try {
      const path = await eel.select_folder()();
      selectedPath = path || '';
      selectedType = selectedPath ? 'folder' : '';
      refreshSelectionUI();
    } catch (e) {
      appendLogLine('[помилка] select_folder: ' + e);
    }
  }

  async function onSelectFile() {
    try {
      const path = await eel.select_file()();
      selectedPath = path || '';
      selectedType = selectedPath ? 'file' : '';
      refreshSelectionUI();
    } catch (e) {
      appendLogLine('[помилка] select_file: ' + e);
    }
  }

  function onRunTask() {
    if (!selectedPath || !selectedType) {
      appendLogLine('[помилка] спочатку оберіть файл або папку.');
      return;
    }
    expandLogCollapse();
    eel.run_task(selectedPath, selectedType);
  }

  async function onExportExcel() {
    try {
      const currentParsedData = await eel.get_current_parsed_data()();
      if (!currentParsedData || !currentParsedData.length) {
        appendLogLine('[помилка] немає даних для експорту');
        return;
      }
      const response = await eel.save_to_excel_with_dialog(currentParsedData)();
      if (!response) return;
      if (response.ok) {
        expandLogCollapse();
        on_registry_saved(currentParsedData.length, response.path);
        return;
      }
      if (response.error === 'user_canceled') {
        return;
      }
      window.alert(response.error || 'Помилка збереження');
    } catch (e) {
      window.alert(String(e));
    }
  }

  function openModal(el) {
    if (!el) return;
    el.hidden = false;
    el.setAttribute('aria-hidden', 'false');
  }

  function closeModal(el) {
    if (!el) return;
    el.hidden = true;
    el.setAttribute('aria-hidden', 'true');
  }

  function onOpenAbout() {
    openModal(document.getElementById('modal-about'));
  }

  function onCloseAbout() {
    closeModal(document.getElementById('modal-about'));
  }

  async function onOpenSettings() {
    try {
      const cfg = await eel.get_settings()();
      const edrpou = document.getElementById('sett-edrpou');
      const name = document.getElementById('sett-name');
      const cols = document.getElementById('sett-cols');
      if (edrpou) {
        edrpou.value =
          cfg && Array.isArray(cfg.my_edrpou_list) && cfg.my_edrpou_list.length
            ? cfg.my_edrpou_list.join('\n')
            : '';
      }
      if (name) {
        name.value =
          cfg && Array.isArray(cfg.my_names_list) && cfg.my_names_list.length
            ? cfg.my_names_list.join('\n')
            : '';
      }
      if (cols) {
        if (cfg && cfg.export_columns) {
          cols.value = Array.isArray(cfg.export_columns)
            ? cfg.export_columns.join('\n')
            : String(cfg.export_columns);
        } else {
          cols.value = '';
        }
      }
      openModal(document.getElementById('modal-settings'));
    } catch (e) {
      appendLogLine('[помилка] get_settings: ' + e);
    }
  }

  async function onSaveSettings() {
    const edrpou = document.getElementById('sett-edrpou');
    const name = document.getElementById('sett-name');
    const cols = document.getElementById('sett-cols');
    const payload = {
      my_edrpou_list: edrpou ? edrpou.value : '',
      my_names_list: name ? name.value : '',
      export_columns: cols ? cols.value : '',
    };
    try {
      const r = await eel.save_settings(payload)();
      if (r && r.ok) {
        closeModal(document.getElementById('modal-settings'));
        appendLogLine('[налаштування] збережено в settings.json');
      } else {
        appendLogLine('[помилка] збереження: ' + ((r && r.error) || 'невідома'));
      }
    } catch (e) {
      appendLogLine('[помилка] save_settings: ' + e);
    }
  }

  async function onShowAnalytics() {
    const modal = document.getElementById('modal-analytics');
    const img = document.getElementById('modal-analytics-img');
    const errEl = document.getElementById('modal-analytics-error');
    if (img) {
      img.hidden = true;
      img.removeAttribute('src');
    }
    if (errEl) {
      errEl.hidden = true;
      errEl.textContent = '';
    }
    openModal(modal);
    try {
      const r = await eel.show_analytics()();
      if (r && r.ok && r.image_base64) {
        if (img) {
          img.src = 'data:image/png;base64,' + r.image_base64;
          img.hidden = false;
        }
      } else {
        if (errEl) {
          errEl.textContent = (r && r.error) || 'Немає даних';
          errEl.hidden = false;
        }
      }
    } catch (e) {
      if (errEl) {
        errEl.textContent = String(e);
        errEl.hidden = false;
      }
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    const btnFolder = document.getElementById('btn-folder');
    const startBtn = document.getElementById('start-btn');
    const btnUpload = document.getElementById('btn-upload-one');
    const btnExcel = document.getElementById('btn-excel');
    const btnAnalytics = document.getElementById('btn-analytics');
    const btnSettings = document.getElementById('btn-settings');
    const btnAbout = document.getElementById('btn-about');

    const modalSettings = document.getElementById('modal-settings');
    const modalAbout = document.getElementById('modal-about');
    const modalAnalytics = document.getElementById('modal-analytics');
    const btnAboutClose = document.getElementById('modal-about-close');
    const btnSettingsCancel = document.getElementById('modal-settings-cancel');
    const btnSettingsSave = document.getElementById('modal-settings-save');
    const btnAnalyticsClose = document.getElementById('modal-analytics-close');
    const logCollapseEl = document.getElementById('log-collapse');
    const logToggleBtn = document.getElementById('log-toggle-btn');

    refreshSelectionUI();

    if (logCollapseEl && logToggleBtn) {
      logCollapseEl.addEventListener('shown.bs.collapse', function () {
        logToggleBtn.textContent = 'Сховати журнал';
        logToggleBtn.setAttribute('aria-expanded', 'true');
      });
      logCollapseEl.addEventListener('hidden.bs.collapse', function () {
        logToggleBtn.textContent = 'Показати журнал';
        logToggleBtn.setAttribute('aria-expanded', 'false');
      });
    }

    if (btnFolder) {
      btnFolder.addEventListener('click', onSelectFolder);
    }
    if (startBtn) {
      startBtn.addEventListener('click', onRunTask);
    }
    if (btnUpload) {
      btnUpload.addEventListener('click', onSelectFile);
    }
    if (btnExcel) {
      btnExcel.addEventListener('click', onExportExcel);
    }
    if (btnAnalytics) {
      btnAnalytics.addEventListener('click', onShowAnalytics);
    }
    if (btnSettings) {
      btnSettings.addEventListener('click', onOpenSettings);
    }
    if (btnAbout) {
      btnAbout.addEventListener('click', onOpenAbout);
    }
    if (btnAboutClose) {
      btnAboutClose.addEventListener('click', onCloseAbout);
    }

    if (btnSettingsCancel) {
      btnSettingsCancel.addEventListener('click', function () {
        closeModal(modalSettings);
      });
    }
    if (btnSettingsSave) {
      btnSettingsSave.addEventListener('click', onSaveSettings);
    }
    if (btnAnalyticsClose) {
      btnAnalyticsClose.addEventListener('click', function () {
        closeModal(modalAnalytics);
      });
    }

    if (modalSettings) {
      modalSettings.addEventListener('click', function (ev) {
        if (ev.target === modalSettings) {
          closeModal(modalSettings);
        }
      });
    }
    if (modalAnalytics) {
      modalAnalytics.addEventListener('click', function (ev) {
        if (ev.target === modalAnalytics) {
          closeModal(modalAnalytics);
        }
      });
    }
    if (modalAbout) {
      modalAbout.addEventListener('click', function (ev) {
        if (ev.target === modalAbout) {
          onCloseAbout();
        }
      });
    }
  });
})();
