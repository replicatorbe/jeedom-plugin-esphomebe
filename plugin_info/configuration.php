<?php
/*
 * Chargé d'ordinaire par Jeedom, cœur déjà en place ; mais le fichier reste
 * joignable en direct, et isConnect() n'y existerait pas.
 */
require_once dirname(__FILE__) . '/../../../core/php/core.inc.php';
include_file('core', 'authentification', 'php');
if (!isConnect('admin')) {
	http_response_code(401);
	die('401 - Unauthorized');
}
?>
<form class="form-horizontal">
	<fieldset>
		<legend><i class="fas fa-cogs"></i> {{Démon}}</legend>
		<div class="form-group">
			<label class="col-lg-4 control-label">{{Port des ordres}}</label>
			<div class="col-lg-2">
				<input class="configKey form-control" data-l1key="socketport" />
			</div>
			<div class="col-lg-6">
				<span class="help-block">{{Port local par lequel Jeedom transmet ses ordres au démon. À changer seulement si ce port est déjà pris sur la machine.}}</span>
			</div>
		</div>
	</fieldset>
</form>
