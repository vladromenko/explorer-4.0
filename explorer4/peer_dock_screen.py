"""Browser target with the same physical geometry and dictionary as the printed dock board."""
import cv2

from .peer_dock_config import (
    DICTIONARY, MARKER_ID, MARKER_SIDE_M, WITNESS_ID, WITNESS_OFFSET_DOWN_M, WITNESS_SIDE_M,
)


def target_html():
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY))
    side = MARKER_SIDE_M * 1000
    offset = WITNESS_OFFSET_DOWN_M * 1000
    small = WITNESS_SIDE_M * 1000
    margin = 12.
    width = side + 2 * margin
    height = side / 2 + offset + small / 2 + 2 * margin
    squares = []
    for ident, edge, cy in ((MARKER_ID, side, 0.), (WITNESS_ID, small, offset)):
        cells = cv2.aruco.generateImageMarker(dictionary, ident, 6)
        for row, col in zip(*((cells == 0).nonzero())):
            x = -edge / 2 + col * edge / 6
            y = cy - edge / 2 + row * edge / 6
            squares.append(f'<rect x="{x:g}" y="{y:g}" width="{edge/6:g}" height="{edge/6:g}"/>')
    svg = (f'<svg id="target" xmlns="http://www.w3.org/2000/svg" aria-label="ArUco 7 and 43" '
           f'viewBox="{-width/2:g} {-width/2:g} {width:g} {height:g}" shape-rendering="crispEdges">'
           + ''.join(squares) + '</svg>')
    return _PAGE.replace('@TARGET@', svg).replace('@WIDTH@', str(width / side)).replace('@HEIGHT@', str(height / side))


_PAGE = """<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Метка совместного подъезда · Explorer 4.0</title>
<style>
*{box-sizing:border-box}body{margin:0;font:16px system-ui;background:#ededed;color:#151515}
main{padding:16px;max-width:940px;margin:auto}h1{font-size:22px;margin:4px 0}
input,button{font:inherit;padding:6px;margin:4px}
#canvas{background:white;display:grid;place-items:center;width:100%;height:min(72vh,900px);overflow:hidden}
#canvas:fullscreen{height:100vh;width:100vw}
#target{display:block;flex:none;background:white;max-width:none;max-height:none}
#warning{padding:16px;text-align:center;color:#781500} [hidden]{display:none!important}
</style><main><h1>Метка на неподвижном экране</h1>
<p>Положите линейку вдоль чёрной стороны большого квадрата и изменяйте его размер до 180 мм.
Центры должны отстоять на 129 мм, нижняя чёрная сторона — 36 мм. Проверьте размер ещё раз в полном экране.
По клавише Esc вернитесь и нажмите «Запомнить размер». Отключите заставку, автоматический поворот и изменение масштаба. Закрепите экран вертикально, уберите блики.
Обе метки должны одновременно читаться в камере. Положение камеры проверяется отдельно.</p>
<label>Чёрная сторона, CSS-пиксели <input id="size" type="number" min="24" max="8000" step="0.1" value="680"></label>
<button id="full">Полный экран</button><button id="save">Запомнить размер на этом экране</button>
<span id="status" role="status"></span></main>
<div id="canvas">@TARGET@<div id="warning" hidden></div></div>
<script>
const size = document.querySelector('#size'), canvas = document.querySelector('#canvas'),
      target = document.querySelector('#target'), warning = document.querySelector('#warning'),
      statusLine = document.querySelector('#status');
const key = 'explorer4.peer-dock-screen.v1';
const settings = () => ({side:Number(size.value), screenWidth:screen.width,
  screenHeight:screen.height, pixelRatio:devicePixelRatio, viewportScale:visualViewport?.scale || 1});
try {
  const stored = JSON.parse(localStorage.getItem(key));
  if (stored && stored.side >= 24 && stored.side <= 8000) {
    size.value = stored.side;
    statusLine.textContent = ['screenWidth','screenHeight','pixelRatio','viewportScale']
      .every(k => settings()[k] === stored[k]) ? 'Сохранённый размер. Сверьте линейкой.' :
      'Изменились экран или масштаб. Повторно измерьте 180 мм.';
  }
} catch {}
let lastFullScreen = null;
function render(){
  const side = Number(size.value), w = side*@WIDTH@, h = side*@HEIGHT@;
  const fits = side >= 24 && side <= 8000 && Math.ceil(w) <= canvas.clientWidth && Math.ceil(h) <= canvas.clientHeight;
  if (fits && document.fullscreenElement) lastFullScreen = JSON.stringify(settings());
  target.hidden = !fits; warning.hidden = fits; target.style.display = fits ? 'block' : 'none';
  target.style.width = w+'px'; target.style.height = h+'px';
  if (!fits) warning.textContent = 'Метка целиком не помещается при выбранном размере. Откройте полный экран или используйте экран больше. Масштаб автоматически не уменьшен.';
}
size.addEventListener('input',render); new ResizeObserver(render).observe(canvas);
window.addEventListener('resize',render); document.addEventListener('fullscreenchange',render);
document.querySelector('#full').onclick=async()=>{try{await canvas.requestFullscreen()}catch{
  statusLine.textContent='Полный экран недоступен в этом браузере. Откройте страницу в отдельном окне.'}};
document.querySelector('#save').onclick=()=>{
  if (target.style.display === 'none' && lastFullScreen !== JSON.stringify(settings())) {statusLine.textContent='Сначала разместите обе метки полностью.';return}
  try {localStorage.setItem(key, JSON.stringify(settings()));statusLine.textContent='Размер сохранён для этого браузера.'}
  catch {statusLine.textContent='Браузер не разрешил сохранить размер.'}
};
render();</script></html>"""
