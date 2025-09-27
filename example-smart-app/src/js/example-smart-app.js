(function(window){
  window.extractData = function() {
    var ret = $.Deferred();
    
    // Version indicator for debugging
    console.log('SMART App JavaScript v3 - Fixed family name handling');
    
    // CORS debugging
    console.log('🔍 CORS Debug Info:');
    console.log('Current origin:', window.location.origin);
    console.log('Current domain:', window.location.hostname);
    
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
      var isStateError = false;
      var errorMsg = '';
      
      if (error && error.message) {
        errorMsg = error.message;
        if (error.message.includes('exp') || error.message.includes('Cannot read properties of null')) {
          isJWTError = true;
        } else if (error.message.includes('state parameter') || error.message.includes('authorization response')) {
          isStateError = true;
        }
      } else if (arguments && arguments.length > 0) {
        var errorStr = JSON.stringify(arguments);
        if (errorStr.includes('exp') || errorStr.includes('null')) {
          isJWTError = true;
        } else if (errorStr.includes('state parameter') || errorStr.includes('authorization response')) {
          isStateError = true;
        }
        errorMsg = errorStr;
      }
      
      // If it's a JWT error, clear tokens and show retry message
      if (isJWTError) {
        console.log('Detected JWT decode error, clearing tokens...');
        clearTokensAndRetry();
        return;
      }
      
      // If it's a state parameter error, show specific guidance
      if (isStateError) {
        console.log('Detected state parameter error - OAuth flow issue');
        $('#loading').hide();
        $('#errors').html('<p style="color: orange;">OAuth authorization error. <a href="javascript:location.reload()">Click here to restart</a> or try launching from Cerner console again.</p>');
        ret.reject();
        return;
      }
      
      // Otherwise show regular error
      $('#loading').hide();
      $('#errors').html('<p style="color: red;">Failed to get FHIR resources. Error: ' + errorMsg + '</p>');
      
      ret.reject();
    }

    function onReady(smart)  {
      console.log('SMART object received:', smart);
      console.log('FHIR Server URL:', smart.server.serviceUrl);
      console.log('FHIR Version:', smart.server.fhirVersion);
      console.log('Authorization URL:', smart.server.authorizeUrl);
      console.log('Granted Scopes:', smart.server.scope);
      console.log('Patient ID:', smart.patient.id);
      
      // Cerner-specific debugging
      if (smart.server.serviceUrl && smart.server.serviceUrl.includes('cerner.com')) {
        console.log('🎯 DETECTED CERNER SERVER - Enhanced debugging enabled');
        console.log('Server metadata:', smart.server);
        console.log('Token response:', smart.tokenResponse);
        
        // Check multiple possible scope locations
        if (smart.tokenResponse && smart.tokenResponse.scope) {
          console.log('✅ Token scopes found:', smart.tokenResponse.scope);
        } else if (smart.server && smart.server.scope) {
          console.log('✅ Server scopes found:', smart.server.scope);
        } else if (smart.scope) {
          console.log('✅ SMART scopes found:', smart.scope);
        } else {
          console.log('❌ NO SCOPES FOUND - This explains the 403 error!');
          console.log('Available smart properties:', Object.keys(smart));
          console.log('Available server properties:', smart.server ? Object.keys(smart.server) : 'No server object');
          console.log('Available tokenResponse properties:', smart.tokenResponse ? Object.keys(smart.tokenResponse) : 'No tokenResponse object');
          
          // Try to extract scopes from JWT token
          if (smart.tokenResponse && smart.tokenResponse.access_token) {
            try {
              // Decode JWT token to check scopes
              var tokenParts = smart.tokenResponse.access_token.split('.');
              if (tokenParts.length === 3) {
                var payload = JSON.parse(atob(tokenParts[1]));
                console.log('JWT Payload:', payload);
                if (payload.scope) {
                  console.log('✅ SCOPES FOUND IN JWT:', payload.scope);
                } else {
                  console.log('❌ No scope field in JWT payload');
                }
              }
            } catch (e) {
              console.log('Error decoding JWT:', e);
            }
          }
        }
      }
      
      if (smart.hasOwnProperty('patient')) {
        console.log('Patient context found:', smart.patient);
        var patient = smart.patient;
        
        // Log the patient read request
        console.log('Making patient read request...');
        var pt = patient.read();
        
        // Log the observation fetch request
        console.log('Making observation fetch request...');
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
      } else if (error && error.status === 503) {
        console.log('503 Service Unavailable - Cerner server maintenance');
        onError(new Error('503 Service Unavailable: Cerner FHIR server is under maintenance. Please try again later.'));
      } else if (error && error.status === 500) {
        console.log('500 Internal Server Error - Cerner server issue');
        onError(new Error('500 Internal Server Error: Cerner FHIR server encountered an error. Please try again.'));
      } else if (error && error.status === 0) {
        console.log('CORS error detected (status 0)');
        onError(new Error('CORS Error: Cross-origin request blocked. This may be due to Cerner server CORS policy or browser security settings.'));
      } else if (error && error.message && error.message.includes('CORS')) {
        console.log('CORS error detected in message');
        onError(new Error('CORS Error: ' + error.message + '. Try using SMART Health IT Sandbox instead.'));
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

          if (typeof patient.name[0] !== 'undefined') {
            try {
              // Handle given names (first names) - ensure it's an array
              if (patient.name[0].given) {
                if (Array.isArray(patient.name[0].given)) {
                  fname = patient.name[0].given.join(' ');
                } else if (typeof patient.name[0].given === 'string') {
                  fname = patient.name[0].given;
                }
              }
              
              // Handle family name - ensure it's an array or handle string
              if (patient.name[0].family) {
                if (Array.isArray(patient.name[0].family)) {
                  lname = patient.name[0].family.join(' ');
                } else if (typeof patient.name[0].family === 'string') {
                  lname = patient.name[0].family;
                }
              }
            } catch (nameError) {
              console.log('Error processing patient name:', nameError);
              fname = 'Unknown';
              lname = 'Unknown';
            }
          } else {
            console.log('No patient name found, using defaults');
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
