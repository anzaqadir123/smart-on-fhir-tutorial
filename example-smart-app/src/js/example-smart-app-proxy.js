(function(window){
  window.extractData = function() {
    var ret = $.Deferred();
    
    // Version indicator for debugging
    console.log('SMART App JavaScript v3 - Backend Proxy Version');
    
    // Backend proxy configuration
    var PROXY_BASE_URL = 'http://localhost:5000/proxy';
    
    function onError(error) {
      console.log('Loading error', error);
      console.log('Error details:', arguments);
      
      var errorMsg = 'Failed to get FHIR resources. ';
      
      if (error && error.message) {
        errorMsg += 'Error: ' + error.message;
      } else if (arguments && arguments.length > 0) {
        errorMsg += 'Details: ' + JSON.stringify(arguments);
      }
      
      // Display error in the UI
      $('#loading').hide();
      $('#errors').html('<p style="color: red;">' + errorMsg + '</p>');
      
      ret.reject();
    }

    function onReady(smart)  {
      console.log('SMART object received:', smart);
      console.log('FHIR Server URL:', smart.server.serviceUrl);
      console.log('Patient ID:', smart.patient.id);
      
      // Cerner-specific debugging
      if (smart.server.serviceUrl && smart.server.serviceUrl.includes('cerner.com')) {
        console.log('🎯 DETECTED CERNER SERVER - Using backend proxy');
        console.log('🔗 Proxy URL:', PROXY_BASE_URL);
      }
      
      if (smart.hasOwnProperty('patient')) {
        console.log('Patient context found:', smart.patient);
        var patient = smart.patient;
        
        // Log the patient read request
        console.log('Making patient read request via proxy...');
        var pt = patient.read();
        
        // Log the observation fetch request
        console.log('Making observation fetch request via proxy...');
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
          
          // Check for different error types
          var error = patientError || obsError;
          
          if (error && error.status === 403) {
            console.log('403 Forbidden error - insufficient scopes');
            onError(new Error('403 Forbidden: Insufficient permissions. Check that patient/Patient.read and patient/Observation.read scopes are granted.'));
          } else if (error && error.status === 502) {
            console.log('502 Bad Gateway - Cerner server issue');
            onError(new Error('502 Bad Gateway: Cerner FHIR server is temporarily unavailable. Please try again in a few minutes.'));
          } else if (error && error.status === 0) {
            console.log('CORS error detected (status 0) - Backend proxy should prevent this');
            onError(new Error('CORS Error: Backend proxy not running. Start the proxy server with: python backend-proxy.py'));
          } else {
            onError(error);
          }
        });

        $.when(pt, obv).done(function(patient, obv) {
          var byCodes = smart.byCodes(obv, 'code');
          var gender = patient.gender;

          var fname = '';
          var lname = '';

          // Debug: Log the patient name structure
          console.log('Patient name structure:', patient.name);
          if (patient.name && patient.name[0]) {
            console.log('First name object:', patient.name[0]);
            console.log('Given name type:', typeof patient.name[0].given, patient.name[0].given);
            console.log('Family name type:', typeof patient.name[0].family, patient.name[0].family);
          }

          if (patient.name && patient.name[0]) {
            // Handle given names (first names)
            if (patient.name[0].given) {
              if (Array.isArray(patient.name[0].given)) {
                fname = patient.name[0].given.join(' ');  // Array of strings
              } else {
                fname = patient.name[0].given; // Single string
              }
            } else {
              fname = ''; // Default if given name is missing
            }

            // Handle family name
            if (patient.name[0].family) {
              if (Array.isArray(patient.name[0].family)) {
                lname = patient.name[0].family.join(' '); // Array of strings
              } else {
                lname = patient.name[0].family; // Single string
              }
            } else {
              lname = ''; // Default if family name is missing
            }
          } else {
            fname = 'Unknown';
            lname = 'Unknown';
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
