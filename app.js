// Сервер для раздачи статических файлов
const http = require('http');
const fs = require('fs');
const path = require('path');

// Порт из переменных окружения BotHost или 3000 по умолчанию
const PORT = process.env.PORT || 3000;

// MIME-типы для разных файлов
const mimeTypes = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon'
};

// Создаем HTTP-сервер
const server = http.createServer((req, res) => {
  console.log(Запрос: ${req.method} ${req.url});
  
  // Нормализуем URL (убираем query string, убираем ведущие слэши для безопасного join)
  let url = (req.url || '/').split('?')[0].replace(/^\/+/, '') || 'index.html';
  
  // Определяем путь к файлу и проверяем, что он внутри public (защита от path traversal)
  const publicDir = path.join(__dirname, 'public');
  const filePath = path.join(publicDir, path.normalize(url));
  const resolvedPath = path.resolve(filePath);
  const resolvedPublic = path.resolve(publicDir);
  if (!resolvedPath.startsWith(resolvedPublic + path.sep) && resolvedPath !== resolvedPublic) {
    res.writeHead(403);
    res.end('Доступ запрещён');
    return;
  }
  const extname = path.extname(resolvedPath);
  const contentType = mimeTypes[extname] || 'text/plain';
  
  // Читаем файл
  fs.readFile(resolvedPath, (error, content) => {
    if (error) {
      if (error.code === 'ENOENT') {
        res.writeHead(404);
        res.end('Файл не найден');
      } else {
        res.writeHead(500);
        res.end(Ошибка сервера: ${error.code});
      }
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content, 'utf-8');
    }
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(✅ Сервер запущен на порту ${PORT});
});
