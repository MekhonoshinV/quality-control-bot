import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

DB_NAME = "quality.db"

def load_data():
    """Загрузка данных из SQLite базы"""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM inspections", conn)
    conn.close()
    
    if len(df) == 0:
        return pd.DataFrame()
    
    df['date'] = pd.to_datetime(df['date'])
    return df

# Инициализация приложения Dash
app = dash.Dash(__name__)

# Макет дашборда
app.layout = html.Div([
    html.H1("🏭 Дашборд контроля качества", style={'textAlign': 'center', 'color': '#2c3e50'}),
    
    html.P("Данные поступают из Telegram-бота в реальном времени", 
           style={'textAlign': 'center', 'color': 'gray'}),
    
    html.Hr(),
    
    # Фильтры
    html.Div([
        html.Div([
            html.Label("Фильтр по дате:", style={'fontWeight': 'bold'}),
            dcc.DatePickerRange(
                id='date-range',
                start_date=(datetime.now() - timedelta(days=30)).date(),
                end_date=datetime.now().date(),
                display_format='DD.MM.YYYY'
            )
        ], style={'width': '48%', 'display': 'inline-block'}),
        
        html.Div([
            html.Label("Фильтр по результату:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='result-filter',
                options=[
                    {'label': 'Все', 'value': 'all'},
                    {'label': 'Годные', 'value': 'pass'},
                    {'label': 'Брак', 'value': 'fail'}
                ],
                value='all'
            )
        ], style={'width': '48%', 'display': 'inline-block', 'float': 'right'})
    ], style={'padding': '20px'}),
    
    # Первая строка графиков
    html.Div([
        html.Div([dcc.Graph(id='quality-gauge')], style={'width': '48%', 'display': 'inline-block'}),
        html.Div([dcc.Graph(id='defect-pie')], style={'width': '48%', 'display': 'inline-block', 'float': 'right'})
    ]),
    
    # Вторая строка графиков
    html.Div([
        html.Div([dcc.Graph(id='quality-timeline')], style={'width': '48%', 'display': 'inline-block'}),
        html.Div([dcc.Graph(id='defect-bar')], style={'width': '48%', 'display': 'inline-block', 'float': 'right'})
    ]),
    
    # Таблица с последними проверками
    html.H3("📋 Последние проверки", style={'marginTop': '30px'}),
    dash.dash_table.DataTable(id='inspections-table'),
    
    # Автообновление каждые 5 секунд
    dcc.Interval(id='interval-component', interval=5000)
], style={'fontFamily': 'Arial, sans-serif', 'padding': '20px'})

# Калбэки для обновления графиков
@app.callback(
    [Output('quality-gauge', 'figure'),
     Output('defect-pie', 'figure'),
     Output('quality-timeline', 'figure'),
     Output('defect-bar', 'figure'),
     Output('inspections-table', 'data'),
     Output('inspections-table', 'columns')],
    [Input('interval-component', 'n_intervals'),
     Input('date-range', 'start_date'),
     Input('date-range', 'end_date'),
     Input('result-filter', 'value')]
)
def update_dashboard(n_intervals, start_date, end_date, result_filter):
    df = load_data()
    
    if df.empty:
        empty_fig = go.Figure()
        empty_fig.add_annotation(text="Нет данных", x=0.5, y=0.5, showarrow=False)
        return [empty_fig] * 4 + [[]] * 2
    
    # Применение фильтров
    if start_date and end_date:
        mask = (df['date'].dt.date >= pd.to_datetime(start_date).date()) & \
               (df['date'].dt.date <= pd.to_datetime(end_date).date())
        df = df[mask]
    
    if result_filter == 'pass':
        df = df[df['result'] == 'pass']
    elif result_filter == 'fail':
        df = df[df['result'] == 'fail']
    
    # 1. Круговая диаграмма - процент годных/брак
    total = len(df)
    if total > 0:
        passed = len(df[df['result'] == 'pass'])
        failed = len(df[df['result'] == 'fail'])
        pass_rate = passed / total * 100
    else:
        passed = failed = 0
        pass_rate = 0
    
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=pass_rate,
        title={'text': "Процент годных изделий (%)"},
        delta={'reference': 50},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': "darkgreen"},
            'steps': [
                {'range': [0, 50], 'color': "red"},
                {'range': [50, 80], 'color': "yellow"},
                {'range': [80, 100], 'color': "lightgreen"}
            ],
            'threshold': {
                'line': {'color': "black", 'width': 2},
                'thickness': 0.75,
                'value': pass_rate
            }
        }
    ))
    fig_gauge.update_layout(height=400)
    
    # 2. Круговая диаграмма дефектов
    defects = df[df['result'] == 'fail'].groupby('defect_category').size().reset_index(name='count')
    if len(defects) > 0:
        fig_pie = px.pie(defects, values='count', names='defect_category', 
                         title="Распределение дефектов по категориям")
    else:
        fig_pie = go.Figure()
        fig_pie.add_annotation(text="Нет данных о дефектах", x=0.5, y=0.5, showarrow=False)
    fig_pie.update_layout(height=400)
    
    # 3. Динамика качества по дням
    daily = df.groupby([df['date'].dt.date, 'result']).size().reset_index(name='count')
    if len(daily) > 0:
        fig_line = px.line(daily, x='date', y='count', color='result',
                           title="Динамика результатов проверок",
                           labels={'date': 'Дата', 'count': 'Количество', 'result': 'Результат'})
    else:
        fig_line = go.Figure()
        fig_line.add_annotation(text="Нет данных", x=0.5, y=0.5, showarrow=False)
    fig_line.update_layout(height=400)
    
    # 4. Гистограмма дефектов
    if len(defects) > 0:
        fig_bar = px.bar(defects, x='defect_category', y='count',
                         title="Количество дефектов по категориям",
                         labels={'defect_category': 'Категория дефекта', 'count': 'Количество'})
    else:
        fig_bar = go.Figure()
        fig_bar.add_annotation(text="Нет данных о дефектах", x=0.5, y=0.5, showarrow=False)
    fig_bar.update_layout(height=400)
    
    # 5. Таблица с последними проверками
    table_df = df.sort_values('date', ascending=False).head(10)
    columns = [{"name": "ID партии", "id": "batch_id"},
               {"name": "Товар", "id": "product_name"},
               {"name": "Проверяющий", "id": "inspector_name"},
               {"name": "Результат", "id": "result"},
               {"name": "Дефект", "id": "defect_category"},
               {"name": "Дата", "id": "date"}]
    data = table_df[['batch_id', 'product_name', 'inspector_name', 'result', 'defect_category', 'date']].to_dict('records')
    
    return fig_gauge, fig_pie, fig_line, fig_bar, data, columns

if __name__ == '__main__':
    app.run(debug=True)