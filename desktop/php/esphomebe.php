<?php
if (!isConnect('admin')) {
	throw new Exception('{{401 - Accès non autorisé}}');
}
$plugin = plugin::byId('esphomebe');
sendVarToJS('eqType', $plugin->getId());
$eqLogics = eqLogic::byType($plugin->getId());
?>

<div class="row row-overflow">
	<div class="col-xs-12 eqLogicThumbnailDisplay">
		<legend><i class="fas fa-cog"></i> {{Gestion}}</legend>
		<div class="eqLogicThumbnailContainer">
			<div class="cursor eqLogicAction logoPrimary" data-action="add">
				<i class="fas fa-plus-circle"></i>
				<br>
				<span>{{Ajouter un module}}</span>
			</div>
			<div class="cursor logoSecondary" id="bt_esphomebeDaemonStatus">
				<i class="fas fa-heartbeat"></i>
				<br>
				<span>{{État des connexions}}</span>
			</div>
			<div class="cursor eqLogicAction logoSecondary" data-action="gotoPluginConf">
				<i class="fas fa-wrench"></i>
				<br>
				<span>{{Configuration}}</span>
			</div>
		</div>

		<legend><i class="fas fa-microchip"></i> {{Mes modules ESPHome}}</legend>
		<?php
		if (count($eqLogics) == 0) {
			echo '<div class="alert alert-info" style="margin:5px;">';
			echo '<b>{{Aucun module pour le moment. Pour démarrer :}}</b>';
			echo '<ol style="margin:5px 0 0 0;padding-left:20px;">';
			echo '<li>{{Installez les dépendances et démarrez le démon depuis la page de configuration du plugin.}}</li>';
			echo '<li>{{Cliquez sur « Ajouter un module », puis saisissez son adresse IP et sa clé API : la valeur de api: encryption: key: dans son YAML.}}</li>';
			echo '<li>{{Enregistrez : le démon se connecte, et les commandes des capteurs du module apparaissent d\'elles-mêmes quelques secondes plus tard.}}</li>';
			echo '</ol>';
			echo '</div>';
		}
		echo '<div class="input-group" style="margin:5px;">';
		echo '<input class="form-control roundedLeft" placeholder="{{Rechercher}}" id="in_searchEqlogic">';
		echo '<div class="input-group-btn">';
		echo '<a id="bt_resetSearch" class="btn" style="width:30px"><i class="fas fa-times"></i></a>';
		echo '<a class="btn roundedRight hidden" id="bt_pluginDisplayAsTable" data-coreSupport="1" data-state="0"><i class="fas fa-grip-lines"></i></a>';
		echo '</div>';
		echo '</div>';
		echo '<div class="eqLogicThumbnailContainer">';
		foreach ($eqLogics as $eqLogic) {
			$opacity = ($eqLogic->getIsEnable()) ? '' : 'disableCard';
			echo '<div class="eqLogicDisplayCard cursor ' . $opacity . '" data-eqLogic_id="' . $eqLogic->getId() . '">';
			echo '<img src="' . $plugin->getPathImgIcon() . '">';
			echo '<br>';
			echo '<span class="name">' . $eqLogic->getHumanName(true, true) . '</span>';
			/* L'état de la connexion d'un coup d'oeil, sans ouvrir chaque module. */
			$online = $eqLogic->getCmd('info', 'online');
			if ($eqLogic->getIsEnable() && $eqLogic->getConfiguration('host') != '') {
				$up = is_object($online) && $online->execCmd() == 1;
				echo '<br><span class="label ' . ($up ? 'label-success' : 'label-danger') . '">'
				   . ($up ? '{{Connecté}}' : '{{Déconnecté}}') . '</span>';
			}
			echo '<span class="hiddenAsCard displayTableRight hidden">';
			echo '<span class="label label-info">' . $eqLogic->getConfiguration('host') . '</span> ';
			echo ($eqLogic->getIsVisible() == 1) ? '<i class="fas fa-eye" title="{{Equipement visible}}"></i>' : '<i class="fas fa-eye-slash" title="{{Equipement non visible}}"></i>';
			echo '</span>';
			echo '</div>';
		}
		echo '</div>';
		?>
	</div>

	<div class="col-xs-12 eqLogic" style="display: none;">
		<div class="input-group pull-right" style="display:inline-flex">
			<span class="input-group-btn">
				<a class="btn btn-default btn-sm eqLogicAction roundedLeft" data-action="configure"><i class="fas fa-cogs"></i><span class="hidden-xs"> {{Configuration avancée}}</span></a>
				<a class="btn btn-default btn-sm eqLogicAction" data-action="copy"><i class="fas fa-copy"></i><span class="hidden-xs"> {{Dupliquer}}</span></a>
				<a class="btn btn-sm btn-success eqLogicAction" data-action="save"><i class="fas fa-check-circle"></i> {{Sauvegarder}}</a>
				<a class="btn btn-sm btn-danger eqLogicAction roundedRight" data-action="remove"><i class="fas fa-minus-circle"></i> {{Supprimer}}</a>
			</span>
		</div>
		<ul class="nav nav-tabs" role="tablist">
			<li role="presentation"><a href="#" class="eqLogicAction" aria-controls="home" role="tab" data-toggle="tab" data-action="returnToThumbnailDisplay"><i class="fas fa-arrow-circle-left"></i></a></li>
			<li role="presentation" class="active"><a href="#eqlogictab" aria-controls="home" role="tab" data-toggle="tab"><i class="fas fa-tachometer-alt"></i><span class="hidden-xs"> {{Équipement}}</span></a></li>
			<li role="presentation"><a href="#commandtab" aria-controls="home" role="tab" data-toggle="tab"><i class="fas fa-list"></i><span class="hidden-xs"> {{Commandes}}</span></a></li>
		</ul>

		<div class="tab-content">
			<div role="tabpanel" class="tab-pane active" id="eqlogictab">
				<br>
				<div class="col-lg-6">
					<form class="form-horizontal">
						<fieldset>
							<legend><i class="fas fa-tag"></i> {{Général}}</legend>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Nom}}</label>
								<div class="col-sm-6">
									<input type="text" class="eqLogicAttr form-control" data-l1key="id" style="display:none;">
									<input type="text" class="eqLogicAttr form-control" data-l1key="name" placeholder="{{Module ESPHome}}">
								</div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Objet parent}}</label>
								<div class="col-sm-6">
									<select class="eqLogicAttr form-control" data-l1key="object_id">
										<option value="">{{Aucun}}</option>
										<?php
										foreach ((jeeObject::buildTree(null, false)) as $object) {
											echo '<option value="' . $object->getId() . '">' . $object->getHumanName(true, true) . '</option>';
										}
										?>
									</select>
								</div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Catégorie}}</label>
								<div class="col-sm-8">
									<?php
									foreach (jeedom::getConfiguration('eqLogic:category') as $key => $value) {
										echo '<label class="checkbox-inline">';
										echo '<input type="checkbox" class="eqLogicAttr" data-l1key="category" data-l2key="' . $key . '">' . $value['name'];
										echo '</label>';
									}
									?>
								</div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Activer}}</label>
								<div class="col-sm-8">
									<input type="checkbox" class="eqLogicAttr" data-l1key="isEnable" checked>
								</div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Visible}}</label>
								<div class="col-sm-8">
									<input type="checkbox" class="eqLogicAttr" data-l1key="isVisible" checked>
								</div>
							</div>
						</fieldset>
					</form>
				</div>

				<div class="col-lg-6">
					<form class="form-horizontal">
						<fieldset>
							<legend><i class="fas fa-microchip"></i> {{Module}}</legend>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Adresse}}</label>
								<div class="col-sm-5">
									<input type="text" class="eqLogicAttr form-control" data-l1key="configuration" data-l2key="host" placeholder="192.168.1.50">
								</div>
								<div class="col-sm-4">
									<span class="help-block" style="margin:0;">{{Adresse IP du module. Réservez-la dans votre routeur.}}</span>
								</div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Port}}</label>
								<div class="col-sm-5">
									<input type="number" class="eqLogicAttr form-control" data-l1key="configuration" data-l2key="port" placeholder="6053">
								</div>
								<div class="col-sm-4">
									<span class="help-block" style="margin:0;">{{6053 sauf si le YAML dit autre chose.}}</span>
								</div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Clé API}}</label>
								<div class="col-sm-5">
									<div class="input-group">
										<input type="password" class="eqLogicAttr form-control roundedLeft" data-l1key="configuration" data-l2key="api_key" autocomplete="new-password" placeholder="abcd…=">
										<span class="input-group-btn">
											<a class="btn btn-default roundedRight" id="bt_esphomebeShowKey" title="{{Afficher la clé}}"><i class="fas fa-eye"></i></a>
										</span>
									</div>
								</div>
								<div class="col-sm-4">
									<span class="help-block" style="margin:0;">{{La valeur de api: encryption: key: du YAML ESPHome. Vide si le module n'est pas chiffré.}}</span>
								</div>
							</div>
						</fieldset>
						<fieldset>
							<legend><i class="fas fa-info-circle"></i> {{Ce que le module annonce}}</legend>
							<span class="help-block">{{Relu à chaque connexion du module. Vide tant qu'il ne s'est jamais connecté : vérifiez alors l'adresse, la clé, et que le démon tourne.}}</span>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Nom ESPHome}}</label>
								<div class="col-sm-8"><span class="label label-default esphomebeInfo" data-key="device_name"></span></div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Modèle}}</label>
								<div class="col-sm-8"><span class="label label-default esphomebeInfo" data-key="model"></span></div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Version ESPHome}}</label>
								<div class="col-sm-8"><span class="label label-default esphomebeInfo" data-key="esphome_version"></span></div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Adresse MAC}}</label>
								<div class="col-sm-8"><span class="label label-default esphomebeInfo" data-key="mac"></span></div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Compilé le}}</label>
								<div class="col-sm-8"><span class="label label-default esphomebeInfo" data-key="compilation_time"></span></div>
							</div>
							<div class="form-group">
								<label class="col-sm-3 control-label">{{Non pris en charge}}</label>
								<div class="col-sm-8"><span class="help-block" style="margin:0;" id="span_esphomebeUnsupported"></span></div>
							</div>
						</fieldset>
					</form>
				</div>
			</div>

			<div role="tabpanel" class="tab-pane" id="commandtab">
				<br>
				<div class="col-xs-12">
					<span class="help-block">{{Les commandes sont créées par le module lui-même, à chaque connexion : un capteur ajouté au YAML apparaît ici après la mise à jour du module. Elles peuvent être renommées ou masquées librement, le plugin ne les réécrit jamais.}}</span>
					<table id="table_cmd" class="table table-bordered table-condensed">
						<thead>
							<tr>
								<th style="width:300px;">{{Nom}}</th>
								<th style="width:130px;">{{Type}}</th>
								<th>{{Identifiant ESPHome}}</th>
								<th style="width:260px;">{{Paramètres}}</th>
								<th style="width:120px;">{{Actions}}</th>
							</tr>
						</thead>
						<tbody></tbody>
					</table>
				</div>
			</div>
		</div>
	</div>
</div>

<?php include_file('desktop', 'esphomebe', 'js', 'esphomebe'); ?>
<?php include_file('core', 'plugin.template', 'js'); ?>
