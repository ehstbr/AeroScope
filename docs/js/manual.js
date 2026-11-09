/* Vanilla JavaScript. The manual works without JS; this only adds convenience. */
(function(){
  'use strict';
  const root=document.documentElement;
  const $=id=>document.getElementById(id);
  const theme=$('theme-btn'),menu=$('toggle-menu'),sidebar=$('side-nav');
  const keys={theme:'aeroscope.manual.theme'};
  try {let saved=localStorage.getItem(keys.theme);if(saved==='light'||saved==='dark')root.dataset.theme=saved;else if(window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches)root.dataset.theme='light';}catch(_e){}
  function syncTheme(){theme.textContent=root.dataset.theme==='light'?'☾':'☼';theme.title=root.dataset.theme==='light'?'Ativar tema escuro':'Ativar tema claro'}
  syncTheme();theme.addEventListener('click',()=>{root.dataset.theme=root.dataset.theme==='light'?'dark':'light';try{localStorage.setItem(keys.theme,root.dataset.theme)}catch(_e){}syncTheme()});
  $('print-btn').addEventListener('click',()=>window.print());
  function closeMenu(){sidebar.classList.remove('is-open');menu.setAttribute('aria-expanded','false');}
  menu.addEventListener('click',()=>{const open=sidebar.classList.toggle('is-open');menu.setAttribute('aria-expanded',String(open))});
  document.querySelectorAll('.sidebar nav a').forEach(a=>a.addEventListener('click',closeMenu));
  document.addEventListener('click',e=>{if(sidebar.classList.contains('is-open')&&!sidebar.contains(e.target)&&!menu.contains(e.target))closeMenu()});
  const links=[...document.querySelectorAll('[data-nav]')];
  const sections=[...document.querySelectorAll('.manual-section')];
  function setActive(id){links.forEach(a=>{let is=a.dataset.nav===id;a.classList.toggle('active',is);if(is)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current')})}
  if('IntersectionObserver'in window){const observer=new IntersectionObserver(entries=>{const shown=entries.filter(e=>e.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top);if(shown.length)setActive(shown[0].target.id)},{rootMargin:'-15% 0px -70% 0px',threshold:0});sections.forEach(s=>observer.observe(s))}else{setActive('introducao')}
  const search=$('manual-search'),results=$('search-results');
  function normal(v){return (v||'').toLocaleLowerCase('pt-BR').normalize('NFD').replace(/[\u0300-\u036f]/g,'')}
  const searchIndex=sections.map(section=>({id:section.id,text:normal(section.textContent)}));
  search.addEventListener('input',()=>{const q=normal(search.value.trim()),tokens=q.split(/\s+/).filter(Boolean);let hits=0;links.forEach(a=>{const match=!tokens.length||tokens.every(word=>searchIndex.find(x=>x.id===a.dataset.nav).text.includes(word));a.hidden=!match;if(match)hits++});results.textContent=tokens.length?`${hits} capítulo${hits===1?'':'s'} encontrado${hits===1?'':'s'} — selecione um resultado`:'17 capítulos • leitura offline';});
  search.addEventListener('keydown',event=>{if(event.key==='Enter'){let first=links.find(x=>!x.hidden);if(first){first.click();search.blur()}}if(event.key==='Escape'&&search.value){search.value='';search.dispatchEvent(new Event('input'))}});
  const progress=$('read-progress');let requested=false;
  function updateProgress(){const max=Math.max(1,document.documentElement.scrollHeight-innerHeight);progress.style.width=(Math.min(100,Math.max(0,100*scrollY/max)))+'%';requested=false}
  addEventListener('scroll',()=>{if(!requested){requested=true;requestAnimationFrame(updateProgress)}},{passive:true});addEventListener('resize',updateProgress);updateProgress();
  const dialog=$('lightbox'),img=$('lightbox-image'),caption=$('lightbox-caption'),idx=$('lightbox-index');
  const figures=[...document.querySelectorAll('button[data-image]')];let imageIndex=0,returnFocus=null;
  function loadImage(){let f=figures[imageIndex];img.src=f.dataset.image;img.alt=f.dataset.caption;caption.textContent=f.dataset.caption;idx.textContent=`${imageIndex+1} / ${figures.length}`;}
  function openImage(n){imageIndex=n;returnFocus=document.activeElement;loadImage();if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');}
  figures.forEach((f,i)=>f.addEventListener('click',()=>openImage(i)));
  $('lightbox-prev').addEventListener('click',()=>{imageIndex=(imageIndex+figures.length-1)%figures.length;loadImage()});
  $('lightbox-next').addEventListener('click',()=>{imageIndex=(imageIndex+1)%figures.length;loadImage()});
  $('lightbox-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
  dialog.addEventListener('close',()=>{img.removeAttribute('src');if(returnFocus&&returnFocus.focus)returnFocus.focus()});
  document.addEventListener('keydown',e=>{if(!dialog.open)return;if(e.key==='ArrowRight'){e.preventDefault();$('lightbox-next').click()}if(e.key==='ArrowLeft'){e.preventDefault();$('lightbox-prev').click()}});
})();
