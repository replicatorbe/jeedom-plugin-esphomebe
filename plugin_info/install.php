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

require_once __DIR__ . '/../../../core/php/core.inc.php';

function esphomebe_install() {
    /* Le callback du démon n'a aucune raison d'être joignable depuis
     * l'extérieur : il ne parle qu'à un processus local. */
    config::save('api::esphomebe::mode', 'localhost', 'core');
}

/*
 * Appelée à chaque mise à jour, dans la requête HTTP : rien de lent ici.
 */
function esphomebe_update() {
    try {
        config::save('api::esphomebe::mode', 'localhost', 'core');
        foreach (esphomebe::byType('esphomebe') as $eqLogic) {
            $eqLogic->createCommands();
        }
    } catch (Throwable $e) {
        log::add('esphomebe', 'error', __('Mise à jour du plugin :', __FILE__) . ' ' . $e->getMessage());
    }
}

/*
 * Appelée aussi à la simple désactivation du plugin : ne rien y détruire.
 */
function esphomebe_remove() {
    try {
        esphomebe::deamon_stop();
    } catch (Throwable $e) {
        log::add('esphomebe', 'error', __('Arrêt du démon :', __FILE__) . ' ' . $e->getMessage());
    }
}
