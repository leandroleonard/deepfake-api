# Instructions

Criar serviços

sudo nano /etc/systemd/system/api.service
sudo nano /etc/systemd/system/celery.service

Recarregar systemd
sudo systemctl daemon-reload

Iniciar serviços

sudo systemctl start api
sudo systemctl start celery

Habilitar no boot
sudo systemctl enable api
sudo systemctl enable celery

Ver logs
sudo journalctl -u api -f
sudo journalctl -u celery -f

