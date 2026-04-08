
from DrissionPage import ChromiumOptions, ChromiumPage
co = ChromiumOptions().set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
paga = ChromiumPage(co)
paga.get('https://www.douyin.com/jingxuan?modal_id=7571747707275757952')
paga.wait(5)
print(paga.html)