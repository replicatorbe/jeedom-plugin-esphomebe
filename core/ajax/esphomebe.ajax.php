<?php
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

try {
    require_once __DIR__ . '/../../../../core/php/core.inc.php';
    include_file('core', 'authentification', 'php');

    /* isConnect('admin') est une égalité stricte de profil. */
    if (!isConnect('admin')) {
        throw new Exception(__('401 - Accès non autorisé', __FILE__));
    }
    /* Depuis la 4.4, ajax::getToken() rend une chaîne vide : l'authentification
     * repose sur la session. */
    ajax::init();

    if (init('action') == 'daemonStatus') {
        $info = esphomebe::deamon_info();
        $answer = esphomebe::sendToDaemon(array('order' => 'status'), true);
        $status = (is_array($answer) && isset($answer['result'])) ? $answer['result'] : null;
        ajax::success(array('deamon' => $info, 'status' => $status));
    }

    throw new Exception(__('Aucune méthode correspondante à :', __FILE__) . ' ' . init('action'));
    /* Throwable et non Exception : les erreurs de PHP 8 n'héritent pas d'Exception. */
} catch (Throwable $e) {
    ajax::error(displayException($e), $e->getCode());
}
