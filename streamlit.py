import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import streamlit as st
import aiohttp
import asyncio
import datetime 
import matplotlib.dates as mdates
import statsmodels
from statsmodels.tsa.seasonal import seasonal_decompose
from sklearn.linear_model import LinearRegression

def load_data():
    uploaded_file = st.file_uploader("Выберите файл", type=["csv"])

    # Сохраняем файл в сессии, чтобы не загружать его снова при обновлении страницы
    if uploaded_file not in st.session_state:
        st.session_state.uploaded_file = None

    if uploaded_file is not None:
        st.session_state.uploaded_file = uploaded_file
        st.write("Файл успешно загружен!")
    
    if st.session_state.uploaded_file is not None:
        return pd.read_csv(st.session_state.uploaded_file, encoding='utf-8')
    return None

def create_column(df):
    df.sort_values(by='timestamp', inplace=True)
    df['moving_average'] = df.groupby('city')['temperature'].transform(lambda x: x.rolling(window=30).mean())
    df['moving_std'] = df.groupby('city')['temperature'].transform(lambda x: x.rolling(window=30).std())
    df['is_anomaly'] = (df['temperature'] > (df['moving_average'] + 2 * df['moving_std'])) | \
                        (df['temperature'] < (df['moving_average'] - 2 * df['moving_std']))
    season_stats = pd.DataFrame()
    season_stats['season_mean_temperature'] = df.groupby(['city', 'season'])['temperature'].mean()
    season_stats['season_std_temperature'] = df.groupby(['city', 'season'])['temperature'].std()
    season_stats = season_stats.reset_index()
    
    # Подсчёт тренда для каждого города с помощью линейной регрессии
    trend_results = []
    for city in df['city'].unique():
        X = np.arange(len(df[df['city'] == city])).reshape(-1, 1)
        y = df[df['city'] == city]['temperature']
        model = LinearRegression()
        model.fit(X, y)
        trend = model.coef_[0]
        trend_results.append((city, trend))
    
    trend_df = pd.DataFrame(trend_results, columns=['city', 'trend_value'])
    df.set_index('timestamp', inplace=True)
    
    return df, trend_df, season_stats

async def get_current_temperature_async(city, api_key):
    url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=ru'

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    temperature = data['main']['temp']
                    timestamp = data['dt']
                    current_month = datetime.datetime.utcfromtimestamp(timestamp).month
                    return temperature, current_month
                elif response.status == 401:
                    return None, "Неверный API-ключ. Пожалуйста, проверьте ключ."
                else:
                    return None, "Ошибка при запросе данных для города."
    except Exception as e:
        return None, f"Произошла ошибка: {str(e)}"

def get_current_weather(city, api_key):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    temperature, current_month = loop.run_until_complete(get_current_temperature_async(city, api_key))

    if temperature is not None:
        st.write(f"Текущая температура в {city}: {temperature}°C")
        return temperature, current_month
    else:
        st.error(current_month)
        return None, None

def get_current_season(current_month):
    if current_month in [1, 2, 12]:
        return 'winter'
    elif current_month in [3, 4, 5]:
        return 'spring'
    elif current_month in [6, 7, 8]:
        return 'summer'
    else:
        return 'autumn'

def check_weather_anomaly(df_city, current_season, temperature, season_stats):
    season_mean_temp = season_stats[(season_stats['city'] == df_city['city'].iloc[0]) & (season_stats['season'] == current_season)]['season_mean_temperature'].mean()
    season_std_temp = season_stats[(season_stats['city'] == df_city['city'].iloc[0]) & (season_stats['season'] == current_season)]['season_std_temperature'].mean()

    if (temperature > (season_mean_temp + 2 * season_std_temp)) or \
       (temperature < (season_mean_temp - 2 * season_std_temp)):
        return f'Температура {temperature}°C аномальная'
    else:
        return f'Температура {temperature}°C находится в пределах нормы'

def get_trend_info(df):
    if df['trend_value'].mean() > 0:
        return f'На основании коэффициента линейной регрессии можно сделать вывод о долгосрочном положительном тренде температуры в городе {df["city"].iloc[0]}'
    else:
        return f'На основании коэффициента линейной регрессии можно сделать вывод о долгосрочном отрицательном тренде температуры в городе {df["city"].iloc[0]}'

# Изображение температуры и скользящего среднего на одном графике
def plot_temperature_and_moving_average(df_city):
    plt.figure(figsize=(15, 8))
    plt.plot(df_city["temperature"], label='Температура', color='steelblue')
    plt.plot(df_city['moving_average'], label='Скользящее среднее за 30 дней', color='orange')
    anomaly_points = df_city[df_city['is_anomaly'] == True]
    plt.scatter(anomaly_points.index, anomaly_points['temperature'], color='red', label='Аномалии', zorder=5)

    plt.gca().xaxis.set_major_locator(mdates.YearLocator())  # Разделитель по годам
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y'))  # Формат отображения: только год
    plt.legend(title='', loc='upper left', fontsize=14)
    plt.xlabel('Даты', fontsize=14)
    plt.ylabel('Температура', fontsize=14)
    plt.title(f"Температура, скользящее среднее и аномалии для города", fontsize=16)
    st.pyplot(plt)

# Разложение временного ряда на компоненты: Тренд, Сезонность, Остатки
def decompose_temperature(df_city, period=365, model='additive'):
    decompose = seasonal_decompose(df_city['temperature'], model=model, period=period)
    plt.figure(figsize=(11, 9))
    decompose.plot()
    plt.suptitle('Разложение временного ряда на компоненты: Тренд, Сезонность, Остатки', fontsize=10, y=1.02)
    st.pyplot(plt)

# Сезонные профили с указанием среднего и стандартного отклонения
def mean_temperature_by_season(season_stats):
    season_order = ['winter', 'spring', 'summer', 'autumn']
    season_stats['season'] = pd.Categorical(season_stats['season'], categories=season_order, ordered=True)
    season_stats = season_stats.sort_values('season')

    plt.figure(figsize=(10, 6))
    plt.fill_between(season_stats['season'], season_stats['season_mean_temperature'] - 2 * season_stats['season_std_temperature'],
                      season_stats['season_mean_temperature'] + 2 * season_stats['season_std_temperature'],
                      color='lightblue', alpha=0.5, label='Стандартное отклонение')

    plt.plot(season_stats['season'], season_stats['season_mean_temperature'], marker='o', label='Средняя температура', color='orange')
    plt.title(f'Сезонные профили с указанием среднего и стандартного отклонения')
    plt.xlabel('Сезон')
    plt.ylabel('Температура°C')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    st.pyplot(plt)

def main():
    st.title("Анализ температурных данных и мониторинг текущей температуры через OpenWeatherMap API")
    df = load_data()
    
    if df is not None:
        df, trend_df, season_stats = create_column(df)
        
        col1, col2 = st.columns(2)
        with col1:
            cities = df['city'].unique()
            city = st.selectbox("Выберите город", cities)
            df_city = df[df['city'] == city]
            trend_df = trend_df[trend_df['city'] == city]
            season_stats = season_stats[season_stats['city'] == city]
        
        with col2:
            api_key = st.text_input("Введите ваш API-ключ OpenWeatherMap", type="password")

        if st.button("Получить текущую температуру"):
            if api_key:
                temperature, current_month = get_current_weather(city, api_key)
                if temperature is not None:
                    current_season = get_current_season(current_month)
                    check_is_anomaly = check_weather_anomaly(df_city, current_season, temperature, season_stats)
                    st.write(check_is_anomaly)
            else:
                st.warning("Пожалуйста, введите ваш API-ключ для получения текущей температуры.")

        res_trend = get_trend_info(trend_df)
        st.write(res_trend)
        
        st.subheader(f"Описательные статистики переменных для {city}")
        st.table(df_city.describe())

        df_city.index = pd.to_datetime(df_city.index)
        
        st.subheader(f"Визуализации")
        plot_temperature_and_moving_average(df_city)
        decompose_temperature(df_city)
        mean_temperature_by_season(season_stats)

if __name__ == "__main__":
    main()
