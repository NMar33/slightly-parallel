"""API routers — one module per surface area.

Registration order matters where literal segments compete with path
parameters (``/api/files/heatmap`` must register before
``/api/files/{file_id}``): ``server.create_app`` includes the specific
routers before the generic lens router.
"""
