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
      
      // Cerner-specific debugging + granted scope logging
      if (smart.server.serviceUrl && smart.server.serviceUrl.includes('cerner.com')) {
        console.log('🎯 DETECTED CERNER SERVER - Using backend proxy');
        console.log('🔗 Proxy URL:', PROXY_BASE_URL);
        var granted = (smart.tokenResponse && smart.tokenResponse.scope) || '(none)';
        console.log('Token scopes:', granted);
      }
      
      if (smart.hasOwnProperty('patient')) {
        console.log('Patient context found:', smart.patient);
        var patient = smart.patient;
        
        // Build Authorization header using SMART access token
        var accessToken = smart && smart.tokenResponse && smart.tokenResponse.access_token;
        // Derive patient id strictly from SMART context (handles function or string forms)
        var patientId = null;
        if (smart && smart.patient) {
          patientId = (typeof smart.patient.id === 'function') ? smart.patient.id() : smart.patient.id;
        }
        if (!patientId) {
          console.log('No patient id in SMART context');
          onError(new Error('No patient in context; cannot query Patient/Observation'));
          return;
        }
        console.log('Using patient from SMART context:', patientId);
        
        // Log the patient read request
        console.log('Making patient read request via proxy...');
        var pt = fetch(PROXY_BASE_URL + '/Patient/' + encodeURIComponent(patientId), {
          headers: {
            'Authorization': 'Bearer ' + accessToken,
            'Accept': 'application/fhir+json'
          }
        }).then(function(resp){ return resp.json(); });
        
        // Helper to fetch any patient-scoped resource via proxy
        function fetchResource(resourceType, extraQuery) {
          var url = PROXY_BASE_URL + '/' + resourceType + '?patient=' + encodeURIComponent(patientId);
          if (extraQuery) {
            url += '&' + extraQuery;
          }
          return fetch(url, {
            headers: {
              'Authorization': 'Bearer ' + accessToken,
              'Accept': 'application/fhir+json'
            }
          })
          .then(function(resp){ return resp.json(); })
          .then(function(bundle){
            var entries = (bundle && bundle.entry) ? bundle.entry : [];
            return entries.map(function(e){ return e.resource; });
          });
        }

        // Log the observation fetch request
        console.log('Making observation fetch request via proxy...');
        var loincCodes = [
          'http://loinc.org|8302-2',
          'http://loinc.org|8462-4',
          'http://loinc.org|8480-6',
          'http://loinc.org|2085-9',
          'http://loinc.org|2089-1',
          'http://loinc.org|55284-4'
        ].join(',');
        var obv = fetchResource('Observation', 'code=' + encodeURIComponent(loincCodes));

        // Additional resource calls similar to Observation
        console.log('Making MedicationRequest fetch via proxy...');
        var meds = fetchResource('MedicationRequest');

        console.log('Making AllergyIntolerance fetch via proxy...');
        var allergies = fetchResource('AllergyIntolerance');

        console.log('Making Condition fetch via proxy...');
        var conditions = fetchResource('Condition');

        console.log('Making DocumentReference fetch via proxy...');
        var documents = fetchResource('DocumentReference');

        Promise.all([pt, obv, meds, allergies, conditions, documents]).then(function(results){
          var patient = results[0];
          var obv = results[1];
          var medsList = results[2];
          var allergiesList = results[3];
          var conditionsList = results[4];
          var documentsList = results[5];

          // Log counts for visibility
          console.log('Fetched Observation:', (obv || []).length);
          console.log('Fetched MedicationRequest:', (medsList || []).length);
          console.log('Fetched AllergyIntolerance:', (allergiesList || []).length);
          console.log('Fetched Condition:', (conditionsList || []).length);
          console.log('Fetched DocumentReference:', (documentsList || []).length);
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
        }).catch(function(err){
          console.log('Proxy fetch error:', err);
          onError(err);
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
