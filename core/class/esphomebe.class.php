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

require_once __DIR__ . '/../../../../core/php/core.inc.php';

class esphomebe extends eqLogic {

    /* Un seul rechargement du démon par requête HTTP, même si trois modules sont enregistrés. */
    private static $_reloadScheduled = false;

    /* ========================================================== DÉMON */

    /*
     * L'état du processus se détermine indépendamment de « launchable » : si
     * l'absence de module configuré rendait aussi l'état « nok », le coeur
     * croirait le démon arrêté et ne l'arrêterait jamais.
     */
    public static function deamon_info() {
        $return = array('log' => __CLASS__ . 'd', 'state' => 'nok', 'launchable' => 'nok');

        $pid_file = jeedom::getTmpFolder(__CLASS__) . '/deamon.pid';
        if (file_exists($pid_file)) {
            $pid = trim(file_get_contents($pid_file));
            if ($pid != '' && @posix_getsid((int) $pid)) {
                $return['state'] = 'ok';
            } else {
                @unlink($pid_file);
            }
        }

        $configured = 0;
        foreach (self::byType(__CLASS__, true) as $eqLogic) {
            if ($eqLogic->getConfiguration('host') != '') {
                $configured++;
            }
        }
        if ($configured > 0) {
            $return['launchable'] = 'ok';
        } else {
            $return['launchable_message'] = __('Aucun module actif n\'est configuré.', __FILE__);
        }
        return $return;
    }

    public static function deamon_start() {
        self::deamon_stop();
        /* Le nouveau démon s'arrêterait aussitôt sur un port encore tenu.
         * Un autre programme qui l'occupe n'est pas tué : le journal du
         * démon le dira. */
        for ($i = 0; $i < 20 && self::portBusy(); $i++) {
            usleep(250000);
        }

        $info = self::deamon_info();
        if ($info['launchable'] != 'ok') {
            throw new Exception(__('Le démon ne peut pas être lancé :', __FILE__) . ' '
                              . $info['launchable_message']);
        }

        $daemon = realpath(__DIR__ . '/../../resources/esphomebed/esphomebed.py');
        $cmd  = system::getCmdPython3(__CLASS__) . escapeshellarg($daemon);
        $cmd .= ' --callback '   . escapeshellarg(self::getCallbackUrl());
        $cmd .= ' --pid '        . escapeshellarg(jeedom::getTmpFolder(__CLASS__) . '/deamon.pid');
        $cmd .= ' --socketport ' . escapeshellarg(config::byKey('socketport', __CLASS__, 55063));
        $cmd .= ' --loglevel '   . escapeshellarg(log::convertLogLevel(log::getLogLevel(__CLASS__)));

        /* La clé API passe par l'entrée standard et jamais par la ligne de
         * commande : ps est lisible par n'importe quel utilisateur local. */
        $full = 'echo ' . escapeshellarg(jeedom::getApiKey(__CLASS__)) . ' | ' . $cmd
              . ' >> ' . log::getPathToLog(__CLASS__ . 'd') . ' 2>&1 &';

        log::add(__CLASS__, 'info', __('Lancement du démon', __FILE__));
        exec($full);

        for ($i = 1; $i <= 30; $i++) {
            $info = self::deamon_info();
            if ($info['state'] == 'ok') {
                message::removeAll(__CLASS__, 'unableStartDeamon');
                return true;
            }
            sleep(1);
        }

        log::add(__CLASS__, 'error', __('Le démon n\'a pas démarré. Consultez le journal', __FILE__)
               . ' ' . __CLASS__ . 'd.');
        message::add(__CLASS__, __('Le démon n\'a pas démarré. Consultez le journal', __FILE__)
                   . ' ' . __CLASS__ . 'd.', null, 'unableStartDeamon');
        return false;
    }

    /* Arrêt propre : SIGTERM, puis jusqu'à dix secondes pour que le démon
     * ferme ses sessions avec les modules et son port d'ordres. Un kill -9
     * immédiat laissait le port pris au moment où deamon_start relançait. */
    public static function deamon_stop() {
        $pid_file = jeedom::getTmpFolder(__CLASS__) . '/deamon.pid';
        if (file_exists($pid_file)) {
            $pid = (int) trim(file_get_contents($pid_file));
            if ($pid > 0 && self::isDaemonPid($pid)) {
                posix_kill($pid, 15);
                for ($i = 0; $i < 40 && self::isDaemonPid($pid); $i++) {
                    usleep(250000);
                }
                if (self::isDaemonPid($pid)) {
                    posix_kill($pid, 9);
                }
            }
            @unlink($pid_file);
        }
        /* Filets de sécurité : un démon lancé à la main, ou dont le fichier de PID
         * a été perdu, garderait le port d'ordres occupé. */
        if (count(system::ps('resources/esphomebed/esphomebed.py')) > 0) {
            system::kill('resources/esphomebed/esphomebed.py', false);
            for ($i = 0; $i < 20 && count(system::ps('resources/esphomebed/esphomebed.py')) > 0; $i++) {
                usleep(250000);
            }
            if (count(system::ps('resources/esphomebed/esphomebed.py')) > 0) {
                system::kill('resources/esphomebed/esphomebed.py');
            }
        }
        system::fuserk(config::byKey('socketport', __CLASS__, 55063));
        foreach (self::byType(__CLASS__) as $eqLogic) {
            $eqLogic->checkAndUpdateCmd('online', 0);
        }
        return true;
    }

    /* Le PID est-il toujours notre démon ? Après un kill -9, il a pu être
     * réattribué à un autre processus. */
    private static function isDaemonPid($_pid) {
        $cmdline = @file_get_contents('/proc/' . (int) $_pid . '/cmdline');
        return $cmdline !== false && strpos($cmdline, 'esphomebed.py') !== false;
    }

    /* Le port d'ordres est-il encore tenu ? Essai d'écoute plutôt que de
     * connexion : un démon encore là ne voit passer aucun ordre vide. */
    private static function portBusy() {
        $server = @stream_socket_server('tcp://127.0.0.1:' . (int) config::byKey('socketport', __CLASS__, 55063), $errno, $errstr);
        if ($server === false) {
            return true;
        }
        fclose($server);
        return false;
    }

    public static function getCallbackUrl() {
        return network::getNetworkAccess('internal', 'http:127.0.0.1:port:comp')
             . '/plugins/esphomebe/core/php/jeeEsphome.php';
    }

    /*
     * Configuration envoyée au démon. Elle est autosuffisante : le démon ne
     * charge pas core.inc.php, il ne peut rien relire du coeur.
     */
    public static function getDaemonConfig() {
        $devices = array();
        foreach (self::byType(__CLASS__, true) as $eqLogic) {
            if ($eqLogic->getConfiguration('host') == '') {
                continue;
            }
            $devices[] = array(
                'id'   => (int) $eqLogic->getId(),
                'name' => $eqLogic->getHumanName(),
                'host' => $eqLogic->getConfiguration('host'),
                'port' => (int) $eqLogic->getConfiguration('port', 6053),
                'key'  => trim($eqLogic->getConfiguration('api_key')),
            );
        }
        return array('devices' => $devices);
    }

    /* Envoi d'un ordre au démon par le socket local. */
    public static function sendToDaemon($_payload, $_waitAnswer = false, $_connectTimeout = 2) {
        $info = self::deamon_info();
        if ($info['state'] != 'ok') {
            return false;
        }
        $port   = (int) config::byKey('socketport', __CLASS__, 55063);
        $socket = @stream_socket_client('tcp://127.0.0.1:' . $port, $errno, $errstr, $_connectTimeout);
        if (!$socket) {
            log::add(__CLASS__, 'debug', __('Le démon n\'a pas accepté la connexion :', __FILE__)
                   . ' ' . $errstr);
            return false;
        }
        $_payload['apikey'] = jeedom::getApiKey(__CLASS__);
        fwrite($socket, json_encode($_payload) . "\n");

        $answer = null;
        if ($_waitAnswer) {
            stream_set_timeout($socket, 5);
            $answer = json_decode(trim((string) fgets($socket, 65536)), true);
        }
        fclose($socket);
        return $_waitAnswer ? $answer : true;
    }

    /*
     * Une seule notification par requête HTTP, envoyée une fois la requête
     * terminée : l'équipement est alors en base et le démon le relira.
     */
    public static function reloadDaemonConfig() {
        if (self::$_reloadScheduled) {
            return;
        }
        self::$_reloadScheduled = true;
        register_shutdown_function(function () {
            try {
                if (esphomebe::deamon_info()['state'] == 'ok') {
                    esphomebe::sendToDaemon(array('order' => 'reload'));
                } else {
                    esphomebe::startDaemonIfAllowed();
                }
            } catch (Throwable $e) {
                log::add('esphomebe', 'error', __('Rechargement du démon :', __FILE__) . ' ' . $e->getMessage());
            }
        });
    }

    /*
     * Le coeur ne vérifie les démons que toutes les cinq minutes : sans ce
     * démarrage, le premier module ajouté restait muet jusque-là, sans que
     * rien ne dise pourquoi. On respecte la gestion automatique : si
     * l'utilisateur l'a coupée, c'est qu'il veut démarrer lui-même.
     */
    public static function startDaemonIfAllowed() {
        if (config::byKey('deamonAutoMode', __CLASS__, 1) != 1) {
            return;
        }
        $info = self::deamon_info();
        if ($info['state'] == 'ok' || $info['launchable'] != 'ok') {
            return;
        }
        $plugin = plugin::byId(__CLASS__);
        if (!is_object($plugin) || $plugin->dependancy_info()['state'] != 'ok') {
            return;
        }
        self::deamon_start();
    }

    /*
     * Un démon qui meurt sans passer par deamon_stop laisse « Connecté » à 1 :
     * le coeur le relancera, mais en attendant rien ne remonte et rien ne le
     * dit. Toutes les cinq minutes, on remet les choses d'aplomb.
     */
    public static function cron5() {
        if (self::deamon_info()['state'] == 'ok') {
            return;
        }
        foreach (self::byType(__CLASS__, true) as $eqLogic) {
            $eqLogic->checkAndUpdateCmd('online', 0);
        }
    }

    /* Le port des ordres ne se recharge pas : le démon l'a ouvert au démarrage. */
    public static function postConfig_socketport($_value) {
        if (self::deamon_info()['state'] == 'ok') {
            message::add(__CLASS__, __('Le port des ordres a changé : redémarrez le démon pour qu\'il soit pris en compte.', __FILE__),
                         null, 'socketportChanged');
        }
    }

    /* ========================================================== ÉQUIPEMENT */

    /*
     * preSave ne lève jamais d'exception à la création : le coeur crée
     * l'équipement avec son seul nom, et une validation stricte rendrait le
     * bouton « Ajouter » définitivement inopérant.
     */
    public function preSave() {
        if ($this->getConfiguration('port') === '' || $this->getConfiguration('port') === null) {
            $this->setConfiguration('port', 6053);
        }
        $this->setConfiguration('host', trim($this->getConfiguration('host')));
        $this->setConfiguration('api_key', trim($this->getConfiguration('api_key')));
        if ($this->getId() == '') {
            return;
        }

        $host = $this->getConfiguration('host');
        if ($host != '' && filter_var($host, FILTER_VALIDATE_IP) === false
            && !preg_match('/^[a-z0-9.\-]+$/i', $host)) {
            throw new Exception(__('L\'adresse du module n\'est pas une adresse IP ni un nom d\'hôte valide.', __FILE__));
        }

        /* La clé de chiffrement d'ESPHome est toujours 32 octets en base64. Une
         * clé tronquée au copier-coller se voit ici, plutôt que comme un module
         * qui refuse la connexion sans que rien ne dise pourquoi. */
        $key = $this->getConfiguration('api_key');
        if ($key != '') {
            $raw = base64_decode($key, true);
            if ($raw === false || strlen($raw) != 32) {
                throw new Exception(__('La clé API doit être la clé de chiffrement du YAML ESPHome (api: encryption: key:), 44 caractères se terminant par « = ».', __FILE__));
            }
        }
    }

    public function postSave() {
        $this->createCommands();
        self::reloadDaemonConfig();
    }

    public function postRemove() {
        self::reloadDaemonConfig();
        return true;
    }

    /* ========================================================== COMMANDES */

    /*
     * Création idempotente : une commande existante n'est jamais réécrite.
     * Son nom, sa visibilité et son historisation appartiennent à l'utilisateur
     * dès qu'il y a touché.
     */
    private function addCmdIfMissing($_logicalId, $_name, $_type, $_subType, $_options = array()) {
        $cmd = $this->getCmd(null, $_logicalId);
        if (is_object($cmd)) {
            return $cmd;
        }

        /* L'unicité SQL porte sur (eqLogic_id, name) : une collision ferait
         * échouer tout l'enregistrement, pas seulement cette commande. */
        $name = mb_substr($_name, 0, 120);
        if (is_object(cmd::byEqLogicIdCmdName($this->getId(), $name))) {
            $name = mb_substr($_name, 0, 80) . ' (' . mb_substr($_logicalId, 0, 40) . ')';
        }

        $cmd = new esphomebeCmd();
        $cmd->setEqLogic_id($this->getId());
        $cmd->setLogicalId($_logicalId);
        $cmd->setName($name);
        $cmd->setType($_type);
        $cmd->setSubType($_subType);
        $cmd->setIsVisible(isset($_options['isVisible']) ? $_options['isVisible'] : 1);
        $cmd->setIsHistorized(isset($_options['isHistorized']) ? $_options['isHistorized'] : 0);
        foreach (array('generic_type' => 'setGeneric_type', 'order' => 'setOrder',
                       'unite' => 'setUnite', 'value' => 'setValue') as $option => $setter) {
            if (isset($_options[$option]) && $_options[$option] !== '') {
                $cmd->$setter($_options[$option]);
            }
        }
        if (isset($_options['configuration'])) {
            foreach ($_options['configuration'] as $key => $value) {
                $cmd->setConfiguration($key, $value);
            }
        }
        if (isset($_options['display'])) {
            foreach ($_options['display'] as $key => $value) {
                $cmd->setDisplay($key, $value);
            }
        }
        $cmd->save();
        return $cmd;
    }

    /* Les commandes propres au plugin, présentes avant même la première connexion. */
    public function createCommands() {
        $this->addCmdIfMissing('online', __('Connecté', __FILE__), 'info', 'binary',
            array('isHistorized' => 1, 'order' => 0, 'isVisible' => 0));
        $this->addCmdIfMissing('reconnect', __('Reconnecter', __FILE__), 'action', 'other',
            array('order' => 1, 'isVisible' => 0));
    }

    /*
     * Le module vient de se décrire : on retient son identité et on crée les
     * commandes des entités nouvelles. Appelé à chaque connexion — c'est ce
     * qui fait apparaître un capteur ajouté au YAML sans rien toucher ici.
     */
    public function syncDevice($_info, $_entities, $_unsupported) {
        $changed = false;
        foreach (array('name' => 'device_name', 'friendly_name' => 'friendly_name', 'mac' => 'mac',
                       'model' => 'model', 'manufacturer' => 'manufacturer',
                       'esphome_version' => 'esphome_version', 'compilation_time' => 'compilation_time',
                       'project_name' => 'project_name', 'project_version' => 'project_version') as $from => $to) {
            $value = isset($_info[$from]) ? (string) $_info[$from] : '';
            if ($this->getConfiguration($to) !== $value) {
                $this->setConfiguration($to, $value);
                $changed = true;
            }
        }
        $unsupported = array();
        foreach ($_unsupported as $entity) {
            $unsupported[] = $entity['type'] . ' : ' . $entity['name'];
        }
        if ($this->getConfiguration('unsupported') !== $unsupported) {
            $this->setConfiguration('unsupported', $unsupported);
            $changed = true;
        }
        if ($changed) {
            /* Écriture directe : un save() normal relancerait postSave, donc un
             * rechargement du démon à chaque connexion du module. */
            $this->save(true);
        }

        $order = 10;
        $created = 0;
        foreach ($_entities as $entity) {
            $created += $this->addEntityCommands($entity, $order);
        }
        if ($created > 0) {
            log::add(__CLASS__, 'info', $this->getHumanName() . ' : ' . $created . ' '
                   . __('commande(s) créée(s) depuis les entités du module', __FILE__));
        }
    }

    /*
     * Crée les commandes qu'une entité décrit. Le démon sait ce qu'est une
     * lumière ou un volet ; ici on ne fait que poser ce qu'il décrit, dans
     * l'ordre donné — les infos avant les actions, pour que chaque action
     * trouve l'info qui lui sert de retour d'état.
     *
     * Les entités de diagnostic (signal Wi-Fi, durée de fonctionnement…) et
     * celles que le YAML désactive par défaut sont créées invisibles : elles
     * restent disponibles pour les scénarios sans encombrer le dashboard.
     *
     * Rend le nombre de commandes créées.
     */
    private function addEntityCommands($_entity, &$_order) {
        $entityVisible = (empty($_entity['disabled_by_default']) && (int) $_entity['entity_category'] == 0) ? 1 : 0;
        $created = 0;

        foreach ($_entity['commands'] as $command) {
            $logicalId = $command['logical_id'];
            $order = $_order++;
            if (is_object($this->getCmd(null, $logicalId))) {
                continue;
            }

            $name = trim($_entity['name'] . ' ' . $command['name']);
            $options = array(
                'order'        => $order,
                'isVisible'    => $entityVisible && (!isset($command['visible']) || $command['visible']) ? 1 : 0,
                'isHistorized' => !empty($command['historized']) ? 1 : 0,
                'generic_type' => isset($command['generic_type']) ? $command['generic_type'] : '',
                'unite'        => isset($command['unit']) ? $command['unit'] : '',
                'configuration' => array(
                    'esphome_domain' => $_entity['domain'],
                    'device_class'   => isset($_entity['device_class']) ? $_entity['device_class'] : '',
                ),
            );
            if ($command['kind'] == 'action') {
                $options['configuration']['esphome_entity'] = $_entity['logical_id'];
                $options['configuration']['esphome_action'] = $command['field'];
                if (!empty($command['value'])) {
                    $state = $this->getCmd('info', $command['value']);
                    if (is_object($state)) {
                        $options['value'] = $state->getId();
                    }
                }
                if (!empty($command['confirm'])) {
                    $options['configuration']['actionConfirm'] = 1;
                }
            }
            if (isset($command['min']) && $command['min'] !== null) {
                $options['configuration']['minValue'] = $command['min'];
            }
            if (isset($command['max']) && $command['max'] !== null) {
                $options['configuration']['maxValue'] = $command['max'];
            }
            if (!empty($command['step'])) {
                $options['display'] = array('parameters' => array('step' => $command['step']));
            }
            if (!empty($command['list'])) {
                $options['configuration']['listValue'] = $command['list'];
            }
            if (!empty($command['repeat'])) {
                /* Un événement répété (deux appuis identiques) doit redéclencher
                 * les scénarios, même si la valeur ne change pas. */
                $options['configuration']['repeatEventManagement'] = 'always';
            }

            $this->addCmdIfMissing($logicalId, $name,
                                   $command['kind'] == 'action' ? 'action' : 'info',
                                   $command['subtype'], $options);
            $created++;
        }
        return $created;
    }

    /* ========================================================== SANTÉ */

    /*
     * STATIQUE : desktop/php/health.php appelle <plugin>::health() en statique.
     * Une méthode d'instance ferait tomber toute la page Santé en erreur 500.
     */
    public static function health() {
        $return = array();
        $daemon = self::deamon_info();
        $daemonUp = ($daemon['state'] == 'ok');
        $return[] = array(
            'test'   => __('Démon en marche', __FILE__),
            'result' => $daemonUp ? __('OK', __FILE__) : __('NOK', __FILE__),
            'advice' => $daemonUp ? '' : __('Sans démon, aucune valeur ne remonte : démarrez-le depuis la configuration du plugin.', __FILE__),
            'state'  => $daemonUp,
        );

        foreach (self::byType(__CLASS__, true) as $eqLogic) {
            $online = $eqLogic->getCmd('info', 'online');
            $connected = $daemonUp && is_object($online) && $online->execCmd() == 1;
            $error = $eqLogic->getCache('last_error', '');
            $return[] = array(
                'test'   => $eqLogic->getHumanName(true) . ' — ' . __('connexion', __FILE__),
                'result' => $connected ? __('OK', __FILE__) : __('NOK', __FILE__),
                'advice' => $connected ? '' : ($error != '' ? $error : __('Vérifiez l\'adresse et la clé API du module.', __FILE__)),
                'state'  => $connected,
            );
        }
        return $return;
    }
}

/*
 * La classe de commande est obligatoire, même réduite au minimum : sans elle
 * le coeur refuse de créer et d'ouvrir un équipement.
 */
class esphomebeCmd extends cmd {

    public function execute($_options = array()) {
        if ($this->getType() != 'action') {
            return;
        }
        $eqLogic = $this->getEqLogic();

        if ($this->getLogicalId() == 'reconnect') {
            $answer = esphomebe::sendToDaemon(array('order' => 'reconnect', 'id' => (int) $eqLogic->getId()), true);
            if (!is_array($answer)) {
                throw new Exception(__('Le démon ne répond pas : impossible de reconnecter.', __FILE__));
            }
            if ($answer['state'] != 'ok') {
                throw new Exception($eqLogic->getHumanName() . ' : ' . $answer['result']);
            }
            return;
        }

        /*
         * L'entité et l'action sont posées à la création. Repli sur l'identifiant
         * logique (switch::relais::on) pour une commande qui en serait privée.
         */
        $entity = $this->getConfiguration('esphome_entity');
        $action = $this->getConfiguration('esphome_action');
        if ($entity == '' || $action == '') {
            $parts = explode('::', $this->getLogicalId());
            $action = array_pop($parts);
            $entity = implode('::', $parts);
        }

        /* La valeur dépend du sous-type : curseur, liste, couleur ou message. */
        $value = null;
        switch ($this->getSubType()) {
            case 'slider':
                $value = isset($_options['slider']) ? $_options['slider'] : null;
                break;
            case 'select':
                $value = isset($_options['select']) ? $_options['select'] : null;
                break;
            case 'color':
                $value = isset($_options['color']) ? $_options['color'] : null;
                break;
            case 'message':
                $value = isset($_options['message']) ? $_options['message'] : null;
                break;
        }
        if ($this->getSubType() != 'other' && $this->getSubType() != 'message' && ($value === null || $value === '')) {
            throw new Exception($this->getHumanName() . ' : ' . __('aucune valeur à envoyer.', __FILE__));
        }

        $answer = esphomebe::sendToDaemon(array(
            'order'      => 'command',
            'id'         => (int) $eqLogic->getId(),
            'logical_id' => $entity,
            'action'     => $action,
            'value'      => $value,
        ), true);
        if (!is_array($answer)) {
            throw new Exception(__('Le démon ne répond pas : la commande n\'a pas été envoyée.', __FILE__));
        }
        if ($answer['state'] != 'ok') {
            throw new Exception($eqLogic->getHumanName() . ' : ' . $answer['result']);
        }
    }
}
