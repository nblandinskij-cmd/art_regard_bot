const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// Обработчик MainButton настраиваем один раз (иначе при каждом клике добавлялся бы новый)
tg.MainButton.onClick(function() {
    const data = {
        action: 'button_pressed',
        timestamp: new Date().toISOString()
    };
    tg.sendData(JSON.stringify(data));
    setTimeout(() => tg.close(), 1000);
});

document.addEventListener('DOMContentLoaded', function() {
    const mainButton = document.getElementById('mainButton');
    
    if (mainButton) {
        mainButton.addEventListener('click', function() {
            if (tg.HapticFeedback) {
                tg.HapticFeedback.impactOccurred('medium');
            }
            tg.MainButton.setText('ГОТОВО');
            tg.MainButton.show();
        });
    }
    
    if (tg.initDataUnsafe.user) {
        const user = tg.initDataUnsafe.user;
        console.log('Пользователь:', user.first_name, user.last_name);
    }
});
