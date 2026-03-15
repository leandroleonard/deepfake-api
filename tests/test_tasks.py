from unittest.mock import patch
from app.services.deepfake_tasks import process_deepfake_analysis
from app.models.analysis import Analysis
from app.enums import StatusEnum

def test_process_deepfake_success(db):
    # Criar análise fake
    analysis = Analysis(
        user_id="fake-user-id",
        media_type="image",
        media_id="fake-media-id",
        status=StatusEnum.pending
    )
    db.add(analysis)
    db.commit()

    # Mock do subprocess
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = '{"fake": true}'
        mock_run.return_value.returncode = 0

        # Executar task
        process_deepfake_analysis(analysis.id)

        # Verificar resultado
        db.refresh(analysis)
        assert analysis.status == StatusEnum.completed