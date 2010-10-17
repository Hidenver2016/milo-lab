
/* Various callbacks */
var updateTempField = function(event, ui) {
	$("#tempField").val(ui.value);
};
var updatePHField = function(event, ui) {
	$("#phField").val(ui.value);
};
var updateISField = function(event, ui) {
	$("#ionStrengthField").val(ui.value);
};
var toggleAdvancedSettings = function() {
	$("#searchOptions").toggle();
	$("#advancedSettings").toggle();
}
	
$(document).ready(function(){
	// Set up autocomplete
	var options = {
	  serviceUrl: '/suggest',
	  delimiter: /(\+|=|<=>|=>)*\s+\d*/
	};
	var queryField = $('#queryField');
	if (queryField) {
		queryField.autocomplete(options);
	}
	
	// Advanced settings sliders.
	var tempSlider = $("#tempSlider");
	var phSlider = $("#phSlider");
	var ionStrengthSlider = $("#ionStrengthSlider");
	
	if (tempSlider) {
		tempSlider.slider({
			min: 0.0,
		    max: 500.0,
		    step: 0.5,
		    value: $("#tempField").val(),
		    slide: updateTempField,
		    change: updateTempField});
	}	
	if (phSlider) {
		phSlider.slider({
			min: 0.0,
	       	max: 14.0,
	       	step: 0.25,
	       	value: $("#phField").val(),
	       	slide: updatePHField,
	       	change: updatePHField});
	}
	if (ionStrengthSlider) {
		ionStrengthSlider.slider({
			min: 0.0,
	       	max: 0.5,
	       	step: 0.025,
	       	value: $("#ionStrengthField").val(),
	       	slide: updateISField,
	       	change: updateISField});	
	}


	var advancedSettingsLink = $("#advancedSettingsLink");
	if (advancedSettingsLink) {
		advancedSettingsLink.click(toggleAdvancedSettings);
	}
});