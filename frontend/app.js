const $ = (q)=>document.querySelector(q);

const i18n = {
  ru: {
    resource_title: "Ресурс",
    resource_hint: "Наполняй себя мягко. Ресурс — это дыхание, которое ты разрешил.",
    vibrate: "Вибро при завершении",
    quick_log_title: "Короткая запись",
  },
  en: {
    resource_title: "Resource",
    resource_hint: "Fill yourself gently. Resource is the breath you allow.",
    vibrate: "Vibration on finish",
    quick_log_title: "Quick entry",
  }
};

async function loadMode(){
  try{
    const r = await fetch('/mode'); const j = await r.json();
    $('#mode').textContent = j.mode === 'bot' ? "режим: бот" : "режим: офлайн";
  }catch(e){ $('#mode').textContent = "режим: неизвестен"; }
}

function applyLang(lang){
  const t = i18n[lang] || i18n.ru;
  $('#t_resource_title').textContent = t.resource_title;
  $('#t_resource_hint').textContent = t.resource_hint;
  $('#t_vibrate').textContent = t.vibrate;
  $('#t_quick_log_title').textContent = t.quick_log_title;
}

function breathSequence(){
  // 3 шага по 4 секунды (можно адаптировать)
  const steps = [ {p:33, label:'1/3'}, {p:66,label:'2/3'}, {p:100,label:'3/3'} ];
  let i=0;
  $('#btnStart').disabled = true;
  const tick = ()=>{
    const s = steps[i];
    $('#fill').style.width = s.p + '%';
    $('#counter').textContent = s.label;
    i++;
    if(i<steps.length){
      setTimeout(tick, 4000);
    }else{
      // вибро (если включено)
      if($('#vibrateToggle').checked && navigator.vibrate){
        navigator.vibrate(40);
      }
      $('#btnStart').disabled = false;
    }
  };
  tick();
}

async function quickLog(){
  const text = $('#mood').value.trim();
  if(!text){ return; }
  try{
    const r = await fetch('/api/v1/journal', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text})});
    const j = await r.json();
    $('#logStatus').textContent = j.ok ? 'Сохранено' : 'Ошибка';
    setTimeout(()=>$('#logStatus').textContent='', 1500);
    $('#mood').value = '';
  }catch(e){ $('#logStatus').textContent = 'Ошибка сети'; }
}

async function pingBot(){
  try{
    await fetch('/webhook', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message:{text:"Привет из веб-приложения", chat:{id:0}}})
    });
    // это лишь “псевдо”—в реальности писать боту из веба не будем, это демо
  }catch(e){}
}

document.addEventListener('DOMContentLoaded', ()=>{
  loadMode();
  applyLang('ru');
  $('#lang').addEventListener('change', e=>applyLang(e.target.value));
  $('#btnStart').addEventListener('click', breathSequence);
  $('#btnLog').addEventListener('click', quickLog);
  $('#btnPingBot').addEventListener('click', pingBot);

  // Telegram Mini App UX улучшение (если открыт внутри TG)
  if(window.Telegram && Telegram.WebApp){
    Telegram.WebApp.expand();
    Telegram.WebApp.ready();
  }
});
