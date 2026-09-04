

def test_terminal_solo_menus_por_defecto_y_editable(client, admin_headers):
    assert client.get("/api/config").json()["terminal_solo_menus"] is True
    r = client.put("/api/config", json={"terminal_solo_menus": False}, headers=admin_headers)
    assert r.json()["terminal_solo_menus"] is False
    assert client.get("/api/config").json()["terminal_solo_menus"] is False
