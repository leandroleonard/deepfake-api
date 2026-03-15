import io

def test_create_analysis(client, db):
    # Registrar usuário
    client.post("/api/v1/auth/register", json={
        "name": "Test User",
        "email": "test@example.com",
        "password": "password123"
    })
    login_res = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "password123"
    })
    token = login_res.json()["access_token"]

    # Upload de imagem fake
    image = io.BytesIO(b"fake image data")
    response = client.post(
        "/api/v1/analysis/",
        files={"file": ("test.jpg", image, "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"