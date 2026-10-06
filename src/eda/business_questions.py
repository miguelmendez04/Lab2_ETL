import pandas as pd


def _miles(x):
    return f"{x:,.0f}".replace(",", ".")


def _pct(x, dec=1):
    return f"{x:.{dec}f}".replace(".", ",") + "%"


def _dec(x, dec=2):
    return f"{x:.{dec}f}".replace(".", ",")


def calcular_preguntas_negocio(df_ventas, df_logistica):
    """
    PARTE 6. PREGUNTAS DE NEGOCIO
    10 preguntas resueltas con pandas sobre los datos originales (sin limpiar).
    Devuelve una lista de dicts: pregunta, respuesta (texto) y detalle (Series/DataFrame o None).
    """
    v, l = df_ventas, df_logistica

    # costo_envio y ciudad_destino se repiten en cada evento: se toma un valor por pedido
    pedidos_log = l.groupby("pedido_id").agg(
        ciudad_destino=("ciudad_destino", "first"),
        costo_envio=("costo_envio", "first"),
    ).reset_index()

    res = []

    # 1. Canal con mayor venta neta acumulada
    neto_canal = v.groupby("canal")["valor_neto"].sum().sort_values(ascending=False)
    res.append({"pregunta": "¿Cuál es el canal con mayor venta neta acumulada?",
                "respuesta": f"{neto_canal.index[0]}, con ${_miles(neto_canal.iloc[0])} "
                             f"({_pct(neto_canal.iloc[0] / neto_canal.sum() * 100)} del total).",
                "detalle": neto_canal})

    # 2. Categoría con más unidades vendidas en Bogotá D.C. (y contraste con el valor)
    bog = v[v["ciudad"] == "Bogotá D.C."]
    bog_unid = bog.groupby("categoria")["cantidad"].sum().sort_values(ascending=False)
    bog_neto = bog.groupby("categoria")["valor_neto"].sum().sort_values(ascending=False)
    contraste = ("" if bog_neto.index[0] == bog_unid.index[0] else
                 f" Sin embargo, en valor neto lidera {bog_neto.index[0]} (${_miles(bog_neto.iloc[0])}): "
                 "vende menos unidades, pero más caras.")
    res.append({"pregunta": "¿Cuál es la categoría con mayor número de productos vendidos en Bogotá D.C.?",
                "respuesta": f"{bog_unid.index[0]}, con {_miles(bog_unid.iloc[0])} unidades.{contraste}",
                "detalle": pd.DataFrame({"unidades": bog_unid, "valor_neto": bog_neto})})

    # 3. Recurrencia de clientes
    compras = v["id_cliente"].value_counts()
    recurrentes = compras[compras > 1]
    pct_ventas_rec = v["id_cliente"].isin(recurrentes.index).mean() * 100
    dist = compras.value_counts().sort_index().rename_axis("compras_por_cliente").rename("clientes")
    res.append({"pregunta": "¿Qué tan recurrentes son los clientes?",
                "respuesta": f"De {_miles(len(compras))} clientes, {_miles(len(recurrentes))} "
                             f"({_pct(len(recurrentes) / len(compras) * 100)}) compraron más de una vez y generan el "
                             f"{_pct(pct_ventas_rec)} de las ventas. El cliente más frecuente compró {compras.max()} veces.",
                "detalle": dist})

    # 4. Peso del descuento frente al valor bruto
    pct_desc = v["valor_descuento"].sum() / v["valor_bruto"].sum() * 100
    con_desc = (v["descuento_pct"] > 0).mean() * 100
    res.append({"pregunta": "¿Qué porcentaje representa el valor_descuento frente al valor_bruto?",
                "respuesta": f"{_pct(pct_desc, 2)} del valor bruto total; el {_pct(con_desc)} de las ventas tuvo algún descuento.",
                "detalle": None})

    # 5. Tiempo medio por etapa según transportadora (etapas con transportadora asignada)
    t_transp = l.groupby("transportadora")["tiempo_etapa_horas"].mean().round(2).sort_values()
    res.append({"pregunta": "¿Cuál es el tiempo medio por etapa logística según la transportadora?",
                "respuesta": f"Entre {_dec(t_transp.min())} h ({t_transp.index[0]}) y {_dec(t_transp.max())} h "
                             f"({t_transp.index[-1]}): no hay diferencias relevantes. Solo incluye etapas de "
                             f"transporte; el promedio de todas las etapas es {_dec(l['tiempo_etapa_horas'].mean())} h.",
                "detalle": t_transp})

    # 6. Producto con mayor valor neto y su peso en la categoría
    prod = (v.groupby(["producto", "categoria"])["valor_neto"].sum()
              .sort_values(ascending=False).reset_index())
    top = prod.iloc[0]
    neto_cat = v.groupby("categoria")["valor_neto"].sum()
    peso_cat = top["valor_neto"] / neto_cat[top["categoria"]] * 100
    res.append({"pregunta": "¿Qué producto genera el mayor valor neto y cuánto pesa en su categoría?",
                "respuesta": f"{top['producto']} ({top['categoria']}), con ${_miles(top['valor_neto'])}, frente a "
                             f"${_miles(prod['valor_neto'].iloc[1])} del segundo ({prod['producto'].iloc[1]}). Aporta el "
                             f"{_pct(peso_cat)} del valor neto de {top['categoria']}, y explica por qué esa categoría "
                             f"lidera en valor aunque no en número de transacciones.",
                "detalle": prod.head(5).set_index("producto")})

    # 7. ¿De qué depende el costo de envío? (cruce simple por pedido_id de los datos originales)
    pc = pedidos_log.merge(v[["pedido_id", "categoria", "cantidad", "valor_neto"]], on="pedido_id")
    por_ciudad = pc.groupby("ciudad_destino")["costo_envio"].agg(["mean", "nunique"])
    por_cat = pc.groupby("categoria")["costo_envio"].mean()
    corr_cant = pc["costo_envio"].corr(pc["cantidad"])
    corr_valor = pc["costo_envio"].corr(pc["valor_neto"])
    n_tarifas = pc["costo_envio"].nunique()
    res.append({"pregunta": "¿El costo de envío depende de la ciudad destino, la categoría o el tamaño del pedido?",
                "respuesta": f"No. Las {n_tarifas} tarifas aparecen en "
                             f"{'todas' if (por_ciudad['nunique'] == n_tarifas).all() else 'casi todas'} las ciudades, el "
                             f"costo promedio por ciudad varía entre ${_miles(por_ciudad['mean'].min())} y "
                             f"${_miles(por_ciudad['mean'].max())}, y por categoría entre ${_miles(por_cat.min())} y "
                             f"${_miles(por_cat.max())}. La correlación con la cantidad es {_dec(corr_cant, 3)} y con el "
                             f"valor neto {_dec(corr_valor, 3)}. La tarifa no refleja el destino ni el pedido.",
                "detalle": por_ciudad.rename(columns={"mean": "costo_promedio", "nunique": "tarifas_distintas"})})

    # 8. Porcentaje de eventos con incidencia
    pct_inc = l["incidencia"].notna().mean() * 100
    pedidos_inc = l.loc[l["incidencia"].notna(), "pedido_id"].nunique()
    res.append({"pregunta": "¿Qué porcentaje de los eventos presenta una incidencia registrada?",
                "respuesta": f"{_pct(pct_inc, 2)} de los eventos ({l['incidencia'].notna().sum()}), que afectan a "
                             f"{pedidos_inc} pedidos ({_pct(pedidos_inc / l['pedido_id'].nunique() * 100)}).",
                "detalle": None})

    # 9. Medio de pago según el canal
    cruce = pd.crosstab(v["medio_pago"], v["canal"])
    canales_por_medio = (cruce > 0).sum(axis=1)
    exclusivos = [f"{m} solo en {cruce.columns[cruce.loc[m] > 0][0]}" for m in cruce.index if canales_por_medio[m] == 1]
    compartidos = [m for m in cruce.index if canales_por_medio[m] > 1]
    digitales = [c for c in cruce.columns if c != "Tienda física"]
    efectivo_digital = int(cruce.loc["Efectivo", digitales].sum()) if "Efectivo" in cruce.index else 0
    coherencia = ("La combinación es coherente con el negocio: no hay pagos en efectivo en canales digitales."
                  if efectivo_digital == 0 else
                  f"Hay {efectivo_digital} ventas digitales pagadas en efectivo, lo que debe revisarse.")
    res.append({"pregunta": "¿Cómo se relaciona el medio de pago con el canal de venta?",
                "respuesta": f"Hay medios exclusivos de un canal: {'; '.join(exclusivos)}. "
                             f"{', '.join(compartidos)} se usan en más de un canal. {coherencia}",
                "detalle": cruce})

    # 10. Valor neto promedio por transacción en cada ciudad
    neto_ciudad = v.groupby("ciudad")["valor_neto"].mean().round(0).sort_values(ascending=False)
    res.append({"pregunta": "¿Cuál es el valor neto promedio por transacción en cada ciudad?",
                "respuesta": f"Mayor en {neto_ciudad.index[0]} (${_miles(neto_ciudad.iloc[0])}) y menor en "
                             f"{neto_ciudad.index[-1]} (${_miles(neto_ciudad.iloc[-1])}).",
                "detalle": neto_ciudad})

    return res


def responder_preguntas_negocio(df_ventas, df_logistica):
    print("\n" + "#"*60)
    print(" PARTE 6: 10 PREGUNTAS DE NEGOCIO")
    print("#"*60)
    for i, r in enumerate(calcular_preguntas_negocio(df_ventas, df_logistica), start=1):
        print(f"\n{i}. {r['pregunta']}\n   R: {r['respuesta']}")
        if r["detalle"] is not None:
            print(r["detalle"])
