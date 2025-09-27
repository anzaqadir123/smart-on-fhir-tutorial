(function(window){
  window.extractData = function() {
    var ret = $.Deferred();
    
    // Debug function to check token state
    function debugTokenState() {
      try {
        console.log('Checking token state...');
        console.log('sessionStorage keys:', Object.keys(sessionStorage));
        console.log('localStorage keys:', Object.keys(localStorage));
        
        // Check for SMART token in session storage
        var smartToken = sessionStorage.getItem('smart_token_response');
        if (smartToken) {
          console.log('SMART token found:', smartToken);
        } else {
          console.log('No SMART token found in sessionStorage');
        }
      } catch (e) {
        console.log('Error accessing storage:', e);
      }
    }
    
    debugTokenState();
    
    // Function to clear potentially corrupted tokens
    function clearTokensAndRetry() {
      console.log('Clearing potentially corrupted tokens...');
      try {
        // Clear SMART-related tokens from session storage
        sessionStorage.removeItem('smart_token_response');
        sessionStorage.removeItem('smart_authorize_state');
        sessionStorage.removeItem('smart_authorize_nonce');
        
        // Clear from localStorage as well
        localStorage.removeItem('smart_token_response');
        localStorage.removeItem('smart_authorize_state');
        localStorage.removeItem('smart_authorize_nonce');
        
        console.log('Tokens cleared. Please refresh the page to restart authorization.');
        
        // Show user-friendly message
        $('#loading').hide();
        $('#errors').html('<p style="color: orange;">Authorization tokens were corrupted. <a href="javascript:location.reload()">Click here to refresh and restart</a></p>');
        
      } catch (e) {
        console.log('Error clearing tokens:', e);
      }
    }

    function onError(error) {
      console.log('Loading error', error);
      console.log('Error details:', arguments);
      
      // Check if this is a JWT decode error
      var isJWTError = false;
      var errorMsg = '';
      
      if (error && error.message) {
        errorMsg = error.message;
        if (error.message.includes('exp') || error.message.includes('Cannot read properties of null')) {
          isJWTError = true;
        }
      } else if (arguments && arguments.length > 0) {
        var errorStr = JSON.stringify(arguments);
        if (errorStr.includes('exp') || errorStr.includes('null')) {
          isJWTError = true;
        }
        errorMsg = errorStr;
      }
      
      // If it's a JWT error, clear tokens and show retry message
      if (isJWTError) {
        console.log('Detected JWT decode error, clearing tokens...');
        clearTokensAndRetry();
        return;
      }
      
      // Otherwise show regular error
      $('#loading').hide();
      $('#errors').html('<p style="color: red;">Failed to get FHIR resources. Error: ' + errorMsg + '</p>');
      
      ret.reject();
    }

    function onReady(smart)  {
      console.log('SMART object received:', smart);
      
      if (smart.hasOwnProperty('patient')) {
        console.log('Patient context found:', smart.patient);
        var patient = smart.patient;
        var pt = patient.read();
        var obv = smart.patient.api.fetchAll({
                    type: 'Observation',
                    query: {
                      code: {
                        $or: ['http://loinc.org|8302-2', 'http://loinc.org|8462-4',
                              'http://loinc.org|8480-6', 'http://loinc.org|2085-9',
                              'http://loinc.org|2089-1', 'http://loinc.org|55284-4']
                      }
                    }
                  });

        $.when(pt, obv).fail(function(patientError, obsError) {
          console.log('Patient read error:', patientError);
          console.log('Observation fetch error:', obsError);
          onError(patientError || obsError);
        });

        $.when(pt, obv).done(function(patient, obv) {
          var byCodes = smart.byCodes(obv, 'code');
          var gender = patient.gender;

          var fname = '';
          var lname = '';

          if (typeof patient.name[0] !== 'undefined') {
            fname = patient.name[0].given.join(' ');
            lname = patient.name[0].family.join(' ');
          }

          var height = byCodes('8302-2');
          var systolicbp = getBloodPressureValue(byCodes('55284-4'),'8480-6');
          var diastolicbp = getBloodPressureValue(byCodes('55284-4'),'8462-4');
          var hdl = byCodes('2085-9');
          var ldl = byCodes('2089-1');

          var p = defaultPatient();
          p.birthdate = patient.birthDate;
          p.gender = gender;
          p.fname = fname;
          p.lname = lname;
          p.height = getQuantityValueAndUnit(height[0]);

          if (typeof systolicbp != 'undefined')  {
            p.systolicbp = systolicbp;
          }

          if (typeof diastolicbp != 'undefined') {
            p.diastolicbp = diastolicbp;
          }

          p.hdl = getQuantityValueAndUnit(hdl[0]);
          p.ldl = getQuantityValueAndUnit(ldl[0]);

          ret.resolve(p);
        });
      } else {
        console.log('No patient context found in SMART object');
        onError(new Error('No patient context available'));
      }
    }

    // Add error handling for JWT decode issues
    try {
      FHIR.oauth2.ready(onReady, onError);
    } catch (error) {
      console.log('FHIR.oauth2.ready failed:', error);
      if (error.message && error.message.includes('exp')) {
        onError(new Error('Token validation failed - please try launching the app again'));
      } else {
        onError(error);
      }
    }
    
    return ret.promise();

  };

  function defaultPatient(){
    return {
      fname: {value: ''},
      lname: {value: ''},
      gender: {value: ''},
      birthdate: {value: ''},
      height: {value: ''},
      systolicbp: {value: ''},
      diastolicbp: {value: ''},
      ldl: {value: ''},
      hdl: {value: ''},
    };
  }

  function getBloodPressureValue(BPObservations, typeOfPressure) {
    var formattedBPObservations = [];
    BPObservations.forEach(function(observation){
      var BP = observation.component.find(function(component){
        return component.code.coding.find(function(coding) {
          return coding.code == typeOfPressure;
        });
      });
      if (BP) {
        observation.valueQuantity = BP.valueQuantity;
        formattedBPObservations.push(observation);
      }
    });

    return getQuantityValueAndUnit(formattedBPObservations[0]);
  }

  function getQuantityValueAndUnit(ob) {
    if (typeof ob != 'undefined' &&
        typeof ob.valueQuantity != 'undefined' &&
        typeof ob.valueQuantity.value != 'undefined' &&
        typeof ob.valueQuantity.unit != 'undefined') {
          return ob.valueQuantity.value + ' ' + ob.valueQuantity.unit;
    } else {
      return undefined;
    }
  }

  window.drawVisualization = function(p) {
    $('#holder').show();
    $('#loading').hide();
    $('#fname').html(p.fname);
    $('#lname').html(p.lname);
    $('#gender').html(p.gender);
    $('#birthdate').html(p.birthdate);
    $('#height').html(p.height);
    $('#systolicbp').html(p.systolicbp);
    $('#diastolicbp').html(p.diastolicbp);
    $('#ldl').html(p.ldl);
    $('#hdl').html(p.hdl);
  };

})(window);
