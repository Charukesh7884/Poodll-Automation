// Self-contained CloudPoodll module to bypass blocked cdn.jsdelivr.net
(function() {
    window.MathJax = {
        isReady: true,
        Hub: {
            Config: function(){},
            Queue: function(){},
            Register: { StartupHook: function(name, cb) { if(cb) cb(); } }
        }
    };

    var CloudPoodll = {
        version: '1.3.4',
        baseURL: 'https://cloud.poodll.com/local/cpapi/fastpoodllloader.php',
        params: ['parent','appid','timelimit','type','media','updatecontrol','width','height','id',
            'iframeclass','transcode','transcoder','transcribe','subtitle','language','transcribevocab',
            'expiredays','owner','region','token','localloader','localloading','notificationurl',
            'sourcemimetype','speechevents','hints','alreadyparsed','fallback','cloudpoodllurl'],

        setBaseUrl: function(cloudpoodllurl){
            this.baseURL = cloudpoodllurl + '/local/cpapi/fastpoodllloader.php';
        },
        fetchContainers: function(classname){
            return document.getElementsByClassName(classname);
        },
        autoCreateRecorders: function(classname){
            if(!classname){classname='cloudpoodll';}
            var containers = this.fetchContainers(classname);
            for(var ctr=0;ctr<containers.length;ctr++){
                this.insertRecorder(containers[ctr]);
            }
        },
        createRecorder: function(elementid){
            var theelement=document.getElementById(elementid);
            if (theelement) {
                this.insertRecorder(theelement);
            }
        },
        insertRecorder: function(container, attributes){
            if(attributes == undefined) {
                attributes = this.parseAttributes(container);
            }
            var iframe = this.createIframe(attributes);
            if(iframe && container) {
                container.appendChild(iframe);
                container.setAttribute('data-alreadyparsed','true');
            }
        },
        parseAttributes: function(container){
            var attributes = {};
            for(var i=0;i<this.params.length;i++){
                var attr = container.getAttribute('data-' + this.params[i]);
                if(attr!==null){
                    attributes[this.params[i]]=attr;
                }
            }
            return attributes;
        },
        createIframe: function(attributes){
            if(attributes.hasOwnProperty('alreadyparsed') && attributes['alreadyparsed']=='true'){
                return false;
            }
            if(attributes.hasOwnProperty('cloudpoodllurl') ){
                this.setBaseUrl(attributes['cloudpoodllurl']);
            }
            if(!attributes.hasOwnProperty('parent') ){
                attributes['parent']=window.location.protocol + '//' + window.location.hostname;
            }
            if(!attributes.hasOwnProperty('media') ){
                attributes['media']='audio';
            }
            var iframe = document.createElement('iframe');
            var localloading = attributes.hasOwnProperty('localloading') ? attributes['localloading'] : 'auto';
            var iframeurl = this.baseURL + '?';
            for (var property in attributes) {
                iframeurl = iframeurl + property + '=' + attributes[property] + '&';
            }
            iframe.setAttribute('src', iframeurl);
            iframe.setAttribute('width', attributes.width || 350);
            iframe.setAttribute('height', attributes.height || 250);
            iframe.setAttribute('frameBorder', 0);
            iframe.setAttribute('allow', 'camera; microphone; display-capture');
            return iframe;
        },
        theCallback: function(data) {
            if (data.type === 'filesubmitted') {
                var pokeInput = document.getElementById(data.updatecontrol);
                if (pokeInput) pokeInput.value = data.mediaurl;
            }
        },
        initEvents: function(){
            var that = this;
            window.addEventListener('message', function(e) {
                if (e.data && e.data.id && e.data.type) {
                    that.theCallback(e.data);
                }
            });
        }
    };

    window.CloudPoodll = CloudPoodll;

    // Intercept requirejs define
    let origDefine = window.define;
    function registerMocks() {
        if (typeof window.define === 'function') {
            try {
                window.define('https://cdn.jsdelivr.net/gh/justinhunt/cloudpoodll@latest/amd/build/cloudpoodll.min.js', [], function() {
                    return window.CloudPoodll;
                });
                window.define('mod_readaloud/cloudpoodll', [], function() {
                    return window.CloudPoodll;
                });
                window.define('mod_solo/cloudpoodll', [], function() {
                    return window.CloudPoodll;
                });
                window.define('mod_wordcards/cloudpoodll', [], function() {
                    return window.CloudPoodll;
                });
            } catch(e) {}
        }
    }

    Object.defineProperty(window, 'define', {
        configurable: true,
        get() { return origDefine; },
        set(val) {
            origDefine = val;
            registerMocks();
        }
    });

    // Also register on DOMContentLoaded if define already exists
    window.addEventListener('DOMContentLoaded', registerMocks);
})();
