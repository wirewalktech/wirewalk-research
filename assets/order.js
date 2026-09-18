(function () {
  'use strict';
  const API='https://wirewalk-orders.wirewalk-upload.workers.dev';
  const $=s=>document.querySelector(s);
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  let items=[],picked=null,widget=null,token=null,busy=false,live=false;
  const groups={'research-start':['Defined engagements','Fixed fee, stated scope and effort limit. Confirm availability before work starts.'],'research-build':['Build and improve','Planning prices only. Request a written scope and quote before ordering.']};
  const contact=(i,request)=>'/contact/?request='+request+'&service='+encodeURIComponent(i.sku)+'#inquiry';
  function message(text,kind='bad'){ $('#omsg').hidden=!text;$('#omsg').textContent=text;$('#omsg').className='omsg '+kind; }
  function ready(){ $('#go').disabled=busy||!picked||!token||!live; }
  function lock(value){busy=value;document.querySelectorAll('#form input,#form select,#form button,#cat button').forEach(e=>e.disabled=value);ready();}
  function verification(text,retry=false){$('#verify-status').textContent=text;$('#verify-retry').hidden=!retry;}
  window.researchVerifyReady=function(){
    if(!picked||widget!==null||!window.turnstile)return;
    try{widget=window.turnstile.render('#ts',{sitekey:'0x4AAAAAAEuBwz8OpbI3bmtE',size:'flexible',
      callback:t=>{token=t;verification('Verification complete.');ready();},
      'expired-callback':()=>{token=null;verification('Verification expired. Please retry.',true);ready();},
      'error-callback':()=>{token=null;verification('Verification could not load. Retry, or call 516-269-1517.',true);ready();return true;}});
    }catch{verification('Verification could not load. Reload the page or call 516-269-1517.',true);}
  };
  function reset(){token=null;ready();verification('Verifying…');if(widget!==null&&window.turnstile)window.turnstile.reset(widget);else window.researchVerifyReady();}
  $('#verify-retry').addEventListener('click',()=>{if(!window.turnstile){verification('Reload the page to retry verification, or call 516-269-1517.',true);return;}reset();});
  $('#cancel-notice').hidden=!new URLSearchParams(location.search).has('canceled');
  fetch(API+'/catalog?practice=research').then(r=>{if(!r.ok)throw Error();return r.json();}).then(d=>{
    items=d.items||[];live=d.paymentMode==='live';if(!items.length)throw Error();
    $('#cat').innerHTML=(live?'':'<p class="note">Online payments are unavailable. Please request an invoice or call.</p>')+Object.entries(groups).map(([g,[name,note]])=>{
      const rows=items.filter(i=>i.group===g);if(!rows.length)return '';
      return '<section class="grp"><h2>'+name+'</h2><p class="note-l">'+note+'</p>'+rows.map(i=>{
        const quoted=i.priceOnApplication;
        return '<div class="svc"><div class="head"><h3>'+esc(i.name)+'</h3><p>'+esc(i.blurb)+'</p></div><div class="side"><span class="px">'+esc(quoted?'From '+i.listFormatted:i.listFormatted)+'<small>'+esc(quoted?'Written quote required':'Same fee for card or bank transfer')+'</small></span><span class="acts">'+(quoted?'<a class="button secondary" href="'+contact(i,'quote')+'">Request a quote</a>':'<button type="button" class="pay" data-sku="'+esc(i.sku)+'"'+(live?'':' disabled')+'>Select service</button><a class="button secondary" href="'+contact(i,'invoice')+'">Request invoice / PO</a>')+'</span></div></div>';
      }).join('')+'</section>';
    }).join('');
    const requested=new URLSearchParams(location.search).get('service');if(requested)choose(requested);
  }).catch(()=>{$('#cat').innerHTML='<p class="note">Services could not be loaded. <a href="/pricing/">View published rates</a> or <a href="/contact/">contact us to arrange service</a>.</p>';});
  $('#cat').addEventListener('click',e=>{const b=e.target.closest('button[data-sku]');if(b&&!busy)choose(b.dataset.sku);});
  function summary(){if(!picked)return;const ach=$('#o-method').value==='ach';$('#chosen').innerHTML='<b>'+esc(picked.name)+'</b><br>'+esc(ach?picked.ach.fullFormatted:picked.prepay.formatted)+' due now';$('#payment-note').textContent=ach?'Bank transfer uses the same published fee. Payment can take several business days to clear.':'Card payment at the published fee. Work and availability must be confirmed separately.';}
  function choose(sku){
    if(busy||!live)return;const i=items.find(i=>i.sku===sku);if(!i||i.priceOnApplication||!i.prepay)return;
    picked=i;$('#form').hidden=false;message('');
    $('#o-method').innerHTML='<option value="card">Card — '+esc(i.prepay.formatted)+'</option>'+(i.ach&&!i.cardOnly?'<option value="ach">Bank transfer — '+esc(i.ach.fullFormatted)+'</option>':'');
    summary();ready();window.researchVerifyReady();$('#checkout').scrollIntoView({block:'start'});$('#checkout').focus({preventScroll:true});
    setTimeout(()=>{if(!token&&!busy)verification('Still waiting for verification. Retry, reload the page, or call 516-269-1517.',true);},15000);
  }
  $('#o-method').addEventListener('change',summary);
  $('#form').addEventListener('submit',async e=>{
    e.preventDefault();if(busy||!picked||!live)return;
    if(!$('#form').reportValidity())return;
    const name=$('#o-name').value.trim(),email=$('#o-email').value.trim();
    if(name.length<2)return message('Please enter your name.');
    if(!token)return message('Please finish verification first.');
    const body={sku:picked.sku,mode:'full',method:$('#o-method').value,email,name,
      organization:$('#o-org').value.trim()||name,reference:$('#o-ref').value.trim(),practice:'research',token};
    lock(true);message('Opening secure checkout…','wait');
    try{
      const r=await fetch(API+'/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const d=await r.json();if(!r.ok||!d.url)throw Error(d.error||'Checkout could not be started.');
      const u=new URL(d.url);if(u.protocol!=='https:'||u.hostname!=='checkout.stripe.com')throw Error('Unexpected checkout destination.');
      location.assign(u.href);
    }catch(err){lock(false);reset();message(err.message+' If a charge appears, contact us before trying again.');}
  });
})();
