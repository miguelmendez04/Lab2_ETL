def responder_preguntas_negocio(df_ventas, df_logistica):
    """
    PARTE 6. PREGUNTAS DE NEGOCIO (CONOCIMIENTO PREVIO DE PANDAS)
    Solución a 10 preguntas con los datasets originales.
    """
    print("\n" + "#"*60)
    print(" PARTE 6: 10 PREGUNTAS DE NEGOCIO")
    print("#"*60)

    pedidos_log = df_logistica.groupby("pedido_id").agg(
        ciudad_destino=("ciudad_destino", "first"),
        costo_envio=("costo_envio", "first"),
    ).reset_index()
    
    # 1. ¿Cuál es el canal con mayor venta neta acumulada?
    print("1. Canal con mayor venta neta:", df_ventas.groupby('canal')['valor_neto'].sum().idxmax())
    
    # 2. ¿Cuál es la categoría con mayor número de productos vendidos en Bogotá D.C.?
    print("2. Categoría más vendida en Bogotá D.C.:", df_ventas[df_ventas['ciudad'] == 'Bogotá D.C.'].groupby('categoria')['cantidad'].sum().idxmax())
    
    # 3. ¿Cuál es la calificación promedio de los clientes por canal?
    print("\n3. Calificación promedio por canal:\n", df_ventas.groupby('canal')['calificacion_cliente'].mean())
    
    # 4. ¿Qué porcentaje representa el valor_descuento frente al valor_bruto?
    pct_desc = (df_ventas['valor_descuento'].sum() / df_ventas['valor_bruto'].sum()) * 100
    print(f"\n4. Porcentaje global de descuento: {pct_desc:.2f}%")
    
    # 5. ¿Cuál es el tiempo medio por etapa en logística según la transportadora?
    print("\n5. Tiempo medio (horas) por transportadora:\n", df_logistica.groupby('transportadora')['tiempo_etapa_horas'].mean())
    
    # 6. ¿Cuál es la incidencia más recurrente en los despachos?
    mode_inc = df_logistica['incidencia'].mode()[0] if 'incidencia' in df_logistica.columns else 'N/A'
    print(f"\n6. Incidencia más recurrente: {mode_inc}")
    
    # 7. ¿Cuál es el costo total de envío por ciudad destino?
    print("\n7. Costo total de envío por ciudad destino (un costo por pedido):\n",
      pedidos_log.groupby("ciudad_destino")["costo_envio"].sum())
    
    # 8. ¿Qué porcentaje de los eventos presentan una incidencia registrada?
    pct_inc = (df_logistica['incidencia'].notnull().sum() / len(df_logistica)) * 100
    print(f"\n8. Porcentaje de eventos con incidencia: {pct_inc:.2f}%")
    
    # 9. Top 3 de pedidos con mayor costo logístico acumulado:
    costo_max = pedidos_log["costo_envio"].max()
    n_empate = (pedidos_log["costo_envio"] == costo_max).sum()
    top3 = pedidos_log.sort_values(["costo_envio", "pedido_id"], ascending=[False, True]).head(3)
    print(f"\n9. Costo máximo por pedido: {costo_max:,} (empatan {n_empate} pedidos). Primeros 3 por pedido_id:\n",
           top3[["pedido_id", "costo_envio"]])
    
    # 10. ¿Cuál es el valor_neto promedio gastado por transacción en cada ciudad?
    print("\n10. Valor neto promedio por transacción según ciudad:\n", df_ventas.groupby('ciudad')['valor_neto'].mean()) 