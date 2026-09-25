/* This file is part of Jeedom.
 *
 * Jeedom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * Jeedom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with Jeedom. If not, see <http://www.gnu.org/licenses/>.
 */

/* Tout ce qui vient du module est du texte, jamais du balisage. */
function esphomebeEscape(_text) {
  var div = document.createElement('div')
  div.textContent = (_text === null || _text === undefined) ? '' : String(_text)
  return div.innerHTML
}

function esphomebeDaemonStatus() {
  domUtils.ajax({
    type: 'POST',
    url: 'plugins/esphomebe/core/ajax/esphomebe.ajax.php',
    data: { action: 'daemonStatus' },
    dataType: 'json',
    error: function (error) { domUtils.handleAjaxError(error) },
    success: function (result) {
      var info = result.result.deamon
      var lines = '{{Démon}} : ' + esphomebeEscape(info.state)
      if (isset(info.launchable_message) && info.launchable_message !== '') {
        lines += ' (' + esphomebeEscape(info.launchable_message) + ')'
      }
      var status = result.result.status
      if (status && status.devices) {
        for (var i = 0; i < status.devices.length; i++) {
          var d = status.devices[i]
          lines += '<br>' + esphomebeEscape(d.name) + ' (' + esphomebeEscape(d.host) + ') : <b>'
                 + esphomebeEscape(d.state) + '</b>'
          if (d.error) { lines += ' — ' + esphomebeEscape(d.error) }
          if (d.state === 'connecté') { lines += ' — ' + d.entities + ' {{entités}}' }
        }
      }
      bootbox.alert(lines)
    }
  })
}

/* Hook appelé par plugin.template.js une fois l'équipement chargé. */
function printEqLogic(_eqLogic) {
  var span = document.getElementById('span_esphomebeUnsupported')
  if (span !== null) {
    var list = init(_eqLogic.configuration.unsupported, [])
    span.textContent = (Array.isArray(list) && list.length > 0)
      ? list.join(', ')
      : '{{Aucune entité ignorée.}}'
  }
  var key = document.querySelector('.eqLogicAttr[data-l2key="api_key"]')
  if (key !== null) { key.type = 'password' }

  /* Affichage seul : ces valeurs viennent du module, pas du formulaire. En
     eqLogicAttr, elles seraient renvoyées à chaque enregistrement et
     écraseraient la dernière description du module par celle de la page. */
  document.querySelectorAll('.esphomebeInfo').forEach(function (_span) {
    _span.textContent = init(_eqLogic.configuration[_span.getAttribute('data-key')], '')
  })
}

function addCmdToTable(_cmd) {
  if (!isset(_cmd)) {
    var _cmd = { configuration: {} }
  }
  if (!isset(_cmd.configuration)) {
    _cmd.configuration = {}
  }

  var tr = '<td>'
  /* Sans ce champ, chaque enregistrement détruit puis recrée les commandes :
     l'historique est perdu et les scénarios pointent dans le vide. */
  tr += '<span class="cmdAttr" data-l1key="id" style="display:none;"></span>'
  tr += '<div class="input-group">'
  tr += '<input class="cmdAttr form-control input-sm roundedLeft" data-l1key="name" placeholder="{{Nom}}">'
  tr += '<span class="input-group-btn">'
  tr += '<a class="cmdAction btn btn-sm btn-default" data-l1key="chooseIcon" title="{{Choisir une icône}}"><i class="fas fa-icons"></i></a>'
  tr += '</span>'
  tr += '<span class="cmdAttr input-group-addon roundedRight" data-l1key="display" data-l2key="icon" style="font-size:19px;padding:0 5px 0 0!important;"></span>'
  tr += '</div>'
  tr += '</td>'
  tr += '<td>'
  tr += '<span class="type" type="' + init(_cmd.type) + '">' + jeedom.cmd.availableType() + '</span>'
  tr += '<span class="subType" subType="' + init(_cmd.subType) + '"></span>'
  tr += '</td>'
  tr += '<td><code>' + esphomebeEscape(init(_cmd.logicalId)) + '</code></td>'
  tr += '<td>'
  tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="isVisible" checked>{{Afficher}}</label>'
  if (init(_cmd.type) === 'info') {
    tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="isHistorized" checked>{{Historiser}}</label>'
  }
  /* L'unité n'a de sens que pour une valeur numérique ou un curseur. */
  if (init(_cmd.subType) === 'numeric' || init(_cmd.subType) === 'slider') {
    tr += '<input class="cmdAttr form-control input-sm" data-l1key="unite" placeholder="{{Unité}}" style="width:70px;display:inline-block;margin-left:5px;">'
  }
  tr += '<span class="cmdAttr" data-l1key="htmlstate" style="display:inline-block;margin-left:5px;"></span>'
  tr += '</td>'
  tr += '<td>'
  if (is_numeric(_cmd.id)) {
    tr += '<a class="btn btn-default btn-xs cmdAction" data-action="configure"><i class="fas fa-cogs"></i></a> '
    tr += '<a class="btn btn-default btn-xs cmdAction" data-action="test"><i class="fas fa-rss"></i> {{Tester}}</a> '
  }
  tr += '</td>'

  /* Ligne créée en DOM : insertAdjacentHTML sur une table génère un <tbody> par
     insertion. */
  var newRow = document.createElement('tr')
  newRow.innerHTML = tr
  newRow.classList.add('cmd')
  newRow.setAttribute('data-cmd_id', init(_cmd.id))
  document.getElementById('table_cmd').querySelector('tbody').appendChild(newRow)
  newRow.setJeeValues(_cmd, '.cmdAttr')
  /* L'ordre compte : changeType après setJeeValues, jamais l'inverse. */
  jeedom.cmd.changeType(newRow, init(_cmd.subType))
}

/* Les pages de plugin sont chargées en ajax : DOMContentLoaded a déjà eu lieu.
   Les écouteurs sont posés par délégation sur un conteneur qui existe déjà. */
var esphomebeContainer = document.getElementById('div_pageContainer') || document.body

/* Revenir sur la page rejoue ce script : l'écouteur précédent est retiré, sans
   quoi chaque clic serait traité deux fois — et un bouton bascule s'annulerait
   lui-même. */
if (window.esphomebeOnClick) {
  esphomebeContainer.removeEventListener('click', window.esphomebeOnClick)
}
window.esphomebeOnClick = function (_event) {
  var target = _event.target
  if (target === null) { return }

  if (target.closest('#bt_esphomebeDaemonStatus') !== null) {
    _event.preventDefault()
    esphomebeDaemonStatus()
    return
  }
  if (target.closest('#bt_esphomebeShowKey') !== null) {
    _event.preventDefault()
    var key = document.querySelector('.eqLogicAttr[data-l2key="api_key"]')
    if (key !== null) { key.type = (key.type === 'password') ? 'text' : 'password' }
  }
}
esphomebeContainer.addEventListener('click', window.esphomebeOnClick)
