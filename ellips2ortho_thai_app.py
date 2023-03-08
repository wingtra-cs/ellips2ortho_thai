from osgeo import gdal
from scipy.interpolate import griddata
import numpy as np
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st
import zipfile


def interpolate_raster(f, lat, lon):
    band = f.GetRasterBand(1)
    
    # Get Raster Information
    transform = f.GetGeoTransform()
    res = transform[1]
    
    # Define point as row and column
    column = (lon - transform[0]) / transform[1]
    row = (lat - transform[3]) / transform[5]
       
    # Create a 5 x 5 grid of surrounding data
    surround_data = (band.ReadAsArray(np.floor(column-2), np.floor(row-2), 5, 5))
    lon_c = transform[0] + np.floor(column) * res
    lat_c = transform[3] - np.floor(row) * res
    
    # Extract geoid undulation values of surrounding data
    count = -1
    pos = np.zeros((25,2))
    surround_data_v = np.zeros((25,1))
    
    for k in range(-2,3):
        for j in range(-2,3):
            count += 1
            pos[count] = (lon_c+j*res, lat_c-k*res)
            surround_data_v[count] = surround_data[k+2,j+2]
    
    
    # Do a cubic interpolation of surrounding data(
    interp_val = griddata(pos, surround_data_v, (lon, lat), method='cubic')
    
    return interp_val[0]

def main():
    st.set_page_config(layout="wide")
    
    st.title('Ellipsoidal to Orthometric Heights (Thailand)')
    
    st.sidebar.image('./logo.png', width = 260)
    st.sidebar.markdown('#')
    st.sidebar.write('The application uses publicly available data to convert ellipsoidal heights to orthometric based on the TGM2017 geoid model.')
    st.sidebar.write('If you have any questions regarding the application, please contact us at support@wingtra.com.')
    st.sidebar.markdown('#')
    st.sidebar.info('This is a prototype application. Wingtra AG does not guarantee correct functionality. Use with discretion.')
    
    uploaded_csvs = st.file_uploader('Please Select Geotags CSV.', accept_multiple_files=True)
    uploaded = False
    
    for uploaded_csv in uploaded_csvs: 
        if uploaded_csv is not None:
            uploaded = True
    
    # Checking if upload of all CSVs is successful
    
    required_columns = ['# image name',
                        'latitude [decimal degrees]',
                        'longitude [decimal degrees]',
                        'altitude [meter]',
                        'accuracy horizontal [meter]',
                        'accuracy vertical [meter]']
    if uploaded:
        dfs = []
        filenames = []
        df_dict = {}
        
        for ctr, uploaded_csv in enumerate(uploaded_csvs):
            df = pd.read_csv(uploaded_csv, index_col=False)       
            dfs.append(df)
            df_dict[uploaded_csv.name] = ctr
            filenames.append(uploaded_csv.name)
            
            lat = df.columns[1]
            lon = df.columns[2]
            height = df.columns[3]
            
            # Check if CSV is in the correct format
            
            format_check = True
            for column in required_columns:
                if column not in list(df.columns):
                    msg = f'{column} is not in {uploaded_csv.name}.'
                    st.text(msg)
                    format_check = False
            
            if not format_check:
                msg = f'{uploaded_csv.name} is not in the correct format. Delete or reupload to proceed.'
                st.error(msg)
                st.stop()

            # Check if locations are within the United States
            
            url = 'http://api.geonames.org/countryCode?lat='
            geo_request = url + f'{df[lat][0]}&lng={df[lon][0]}&type=json&username=irwinamago'
            
            try:
                country = requests.get(geo_request).json()['countryName']
                
                if country != 'Thailand':
                    msg = f'Locations in {uploaded_csv.name} are outside Thailand. Please remove to proceed.'
                    st.error(msg)
                    st.stop()
            except:
                st.warning('Country information could not be found. Processing will commence but please ensure that the data is within Thailand.', icon="⚠️")
        
        st.success('All CSVs checked and uploaded successfully.')
        
        map_options = filenames.copy()
        map_options.insert(0, '<select>')
        option = st.selectbox('Select geotags CSV to visualize', map_options)
        
        # Option to visualize any of the CSVs
        
        if option != '<select>':
            points_df = pd.concat([dfs[df_dict[option]][lat], dfs[df_dict[option]][lon]], axis=1, keys=['lat','lon'])
            
            st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/satellite-streets-v11',
            initial_view_state=pdk.ViewState(
                latitude=points_df['lat'].mean(),
                longitude=points_df['lon'].mean(),
                zoom=14,
                pitch=0,
             ),
             layers=[
                 pdk.Layer(
                     'ScatterplotLayer',
                     data=points_df,
                     get_position='[lon, lat]',
                     get_color='[70, 130, 180, 200]',
                     get_radius=20,
                 ),
                 ],
             ))

        if uploaded:
            if st.button('CONVERT HEIGHTS'):
                file = 'TGM2017.tif'
                f = gdal.Open(file)
                
                for df in dfs:
                    ortho = []
                        
                    # Height Conversion
                    for la, lo, h in zip(df[lat], df[lon], df[height]):
                        N = interpolate_raster(f, la, lo)
                        ortho.append(h - N)                 
    
                    df[height] = ortho
                    df.rename(columns={height: 'orthometric height TGM2017 [meters]'}, inplace=True)
                
                # Create the zip file, convert the dataframes to CSV, and save inside the zip
                
                if len(dfs) == 1:
                    csv = dfs[0].to_csv(index=False).encode('utf-8')
                    filename = filenames[0].split('.')[0] + '_orthometric.csv'
    
                    st.download_button(
                         label="Download Converted Geotags CSV",
                         data=csv,
                         file_name=filename,
                         mime='text/csv',
                     )
                    
                else:                
                    with zipfile.ZipFile('Converted_CSV.zip', 'w') as csv_zip:
                        for ctr, df in enumerate(dfs):
                            csv_zip.writestr(filenames[ctr].split('.')[0] + '_orthometric.csv', df.to_csv(index=False).encode('utf-8'))   
                    
                    # Download button for the zip file
                    
                    fp = open('Converted_CSV.zip', 'rb')
                    st.download_button(
                        label="Download Converted Geotags CSV",
                        data=fp,
                        file_name='Converted_CSV.zip',
                        mime='application/zip',
                )
        st.stop()
    else:
        st.stop()

if __name__ == "__main__":
    main()
