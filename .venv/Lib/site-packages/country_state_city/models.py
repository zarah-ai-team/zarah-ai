"""
Data models for Country, State, City and Timezone entities.
"""

import json
import os
import unicodedata


class Timezone:
    """
    Represents a timezone with properties like name, GMT offset, abbreviation, etc.

    Attributes:
        name (str): The timezone name (e.g., "America/New_York")
        gmt_offset (int): The GMT offset in seconds
        gmt_offset_name (str): Human-readable GMT offset (e.g., "UTC-05:00")
        abbreviation (str): Timezone abbreviation (e.g., "EST")
        tz_name (str): Full timezone name (e.g., "Eastern Standard Time")
    """
    def __init__(self, name, gmt_offset, gmt_offset_name, abbreviation, tz_name):
        self.name = name
        self.gmt_offset = gmt_offset
        self.gmt_offset_name = gmt_offset_name
        self.abbreviation = abbreviation
        self.tz_name = tz_name

    @classmethod
    def from_dict(cls, data):
        """
        Create a Timezone instance from a dictionary.
        
        Args:
            data (dict): Dictionary containing timezone data with keys:
                zoneName, gmtOffset, gmtOffsetName, abbreviation, tzName
                
        Returns:
            Timezone: A new Timezone instance
        """
        return cls(
            name=data.get('zoneName', ''),
            gmt_offset=data.get('gmtOffset', 0),
            gmt_offset_name=data.get('gmtOffsetName', ''),
            abbreviation=data.get('abbreviation', ''),
            tz_name=data.get('tzName', '')
        )

    def to_dict(self):
        """
        Convert the timezone to a dictionary.
        
        Returns:
            dict: Dictionary representation of this timezone with keys:
                zoneName, gmtOffset, gmtOffsetName, abbreviation, tzName
        """
        return {
            'zoneName': self.name,
            'gmtOffset': self.gmt_offset,
            'gmtOffsetName': self.gmt_offset_name,
            'abbreviation': self.abbreviation,
            'tzName': self.tz_name
        }

    def __repr__(self):
        return f"<Timezone: {self.name}>"


class Country:
    """
    Represents a country with properties like name, ISO code, flag, etc.
    
    Attributes:
        name (str): Full country name (e.g., "United States")
        iso2 (str): ISO 3166-1 alpha-2 country code (e.g., "US")
        phone_code (str): International calling code (e.g., "1")
        flag (str): Emoji flag for the country (e.g., "🇺🇸")
        currency (str): Currency code (e.g., "USD")
        latitude (float): Latitude of country's center
        longitude (float): Longitude of country's center
        timezones (list): List of Timezone objects for this country
        unicode_flag (str): Unicode representation of the flag
    """
    def __init__(self, name, iso2, phone_code, flag, currency, latitude, longitude, timezones=None):
        self.name = name
        self.iso2 = iso2
        self.phone_code = phone_code
        self.flag = flag
        self.currency = currency
        self.latitude = latitude
        self.longitude = longitude
        self.timezones = timezones or []
        
        # Derive unicode flag from emoji flag
        self.unicode_flag = self.flag
    
    @classmethod
    def from_dict(cls, data):
        """Create a Country instance from a dictionary."""
        timezones = [Timezone.from_dict(tz) for tz in data.get('timezones', [])] if data.get('timezones') else []
        
        return cls(
            name=data.get('name', ''),
            iso2=data.get('isoCode', ''),
            phone_code=data.get('phoneCode', ''),
            flag=data.get('flag', ''),
            currency=data.get('currency', ''),
            latitude=data.get('latitude', ''),
            longitude=data.get('longitude', ''),
            timezones=timezones
        )
    
    def to_dict(self):
        """Convert the country to a dictionary."""
        return {
            'name': self.name,
            'isoCode': self.iso2,
            'phoneCode': self.phone_code,
            'flag': self.flag,
            'currency': self.currency,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'timezones': [tz.to_dict() for tz in self.timezones] if self.timezones else []
        }
    
    def __repr__(self):
        return f"<Country: {self.name} ({self.iso2})>"
    
    @staticmethod
    def get_countries():
        """
        Get all countries available in the dataset.
        
        Returns:
            list: A list of Country objects representing all countries in the dataset.
        """
        data_path = os.path.join(os.path.dirname(__file__), 'data', 'country.json')
        with open(data_path, 'r', encoding='utf-8') as f:
            countries_data = json.load(f)
        
        return [Country.from_dict(country) for country in countries_data]
    
    @staticmethod
    def get_country_by_code(country_code):
        """
        Get a country by its ISO code.
        
        Args:
            country_code (str): The ISO 3166-1 alpha-2 country code (e.g., "US" for United States)
            
        Returns:
            Country: Country object matching the code, or None if not found
        """
        if not country_code:
            return None
            
        countries = Country.get_countries()
        for country in countries:
            if country.iso2 == country_code:
                return country
        
        return None


class State:
    """
    Represents a state/province with properties like name, country code, ISO code, etc.
    
    Attributes:
        name (str): Full state name (e.g., "California")
        country_code (str): ISO country code this state belongs to (e.g., "US")
        iso_code (str): State code (e.g., "CA" for California)
        latitude (float): Latitude of state's center
        longitude (float): Longitude of state's center
    """
    def __init__(self, name, country_code, iso_code, latitude=None, longitude=None):
        self.name = name
        self.country_code = country_code
        self.iso_code = iso_code
        self.latitude = latitude
        self.longitude = longitude
    
    @classmethod
    def from_dict(cls, data):
        """Create a State instance from a dictionary."""
        return cls(
            name=data.get('name', ''),
            country_code=data.get('countryCode', ''),
            iso_code=data.get('isoCode', ''),
            latitude=data.get('latitude', None),
            longitude=data.get('longitude', None)
        )
    
    def to_dict(self):
        """Convert the state to a dictionary."""
        return {
            'name': self.name,
            'countryCode': self.country_code,
            'isoCode': self.iso_code,
            'latitude': self.latitude,
            'longitude': self.longitude
        }
    
    def __repr__(self):
        return f"<State: {self.name} ({self.iso_code})>"
    
    @staticmethod
    def get_states():
        """
        Get all states/provinces available in the dataset.
        
        Returns:
            list: A list of State objects representing all states in the dataset
        """
        data_path = os.path.join(os.path.dirname(__file__), 'data', 'state.json')
        with open(data_path, 'r', encoding='utf-8') as f:
            states_data = json.load(f)
        
        return [State.from_dict(state) for state in states_data]
    
    @staticmethod
    def get_states_of_country(country_code):
        """
        Get all states/provinces of a specific country.
        
        Args:
            country_code (str): The ISO 3166-1 alpha-2 country code (e.g., "US")
            
        Returns:
            list: A list of State objects belonging to the specified country,
                  sorted alphabetically by name. Empty list if country not found.
        """
        if not country_code:
            return []
            
        states = State.get_states()
        country_states = [state for state in states if state.country_code == country_code]
        return sorted(country_states, key=lambda x: x.name)
    
    @staticmethod
    def get_state_by_code(country_code, state_code):
        """
        Get a state by its country code and state code.
        
        Args:
            country_code (str): The ISO 3166-1 alpha-2 country code (e.g., "US")
            state_code (str): The state code (e.g., "CA" for California)
            
        Returns:
            State: State object matching the codes, or None if not found
        """
        if not country_code or not state_code:
            return None
            
        states = State.get_states()
        for state in states:
            if state.country_code == country_code and state.iso_code == state_code:
                return state
        
        return None


class City:
    """
    Represents a city with properties like name, country code, state code, etc.
    
    Attributes:
        name (str): City name (e.g., "Los Angeles")
        country_code (str): ISO country code this city belongs to (e.g., "US")
        state_code (str): State code this city belongs to (e.g., "CA")
        latitude (float): Latitude of city's center
        longitude (float): Longitude of city's center
    """
    def __init__(self, name, country_code, state_code, latitude=None, longitude=None):
        self.name = name
        self.country_code = country_code
        self.state_code = state_code
        self.latitude = latitude
        self.longitude = longitude
    
    @classmethod
    def from_dict(cls, data):
        """Create a City instance from a dictionary."""
        return cls(
            name=data.get('name', ''),
            country_code=data.get('countryCode', ''),
            state_code=data.get('stateCode', ''),
            latitude=data.get('latitude', None),
            longitude=data.get('longitude', None)
        )
    
    def to_dict(self):
        """Convert the city to a dictionary."""
        return {
            'name': self.name,
            'countryCode': self.country_code,
            'stateCode': self.state_code,
            'latitude': self.latitude,
            'longitude': self.longitude
        }
    
    def __repr__(self):
        return f"<City: {self.name}>"
    
    @staticmethod
    def get_cities():
        """
        Get all cities available in the dataset.
        
        Returns:
            list: A list of City objects representing all cities in the dataset
                 (note: this can be a large dataset)
        """
        data_path = os.path.join(os.path.dirname(__file__), 'data', 'city.json')
        with open(data_path, 'r', encoding='utf-8') as f:
            cities_data = json.load(f)
        
        return [City.from_dict(city) for city in cities_data]
    
    @staticmethod
    def get_cities_of_state(country_code, state_code):
        """
        Get all cities of a specific state.
        
        Args:
            country_code (str): The ISO 3166-1 alpha-2 country code (e.g., "US")
            state_code (str): The state code (e.g., "CA" for California)
            
        Returns:
            list: A list of City objects belonging to the specified state,
                  sorted alphabetically by name. Empty list if state not found.
        """
        if not country_code or not state_code:
            return []
            
        cities = City.get_cities()
        state_cities = [
            city for city in cities 
            if city.country_code == country_code and city.state_code == state_code
        ]
        return sorted(state_cities, key=lambda x: x.name)
    
    @staticmethod
    def get_cities_of_country(country_code):
        """
        Get all cities of a specific country.
        
        Args:
            country_code (str): The ISO 3166-1 alpha-2 country code (e.g., "US")
            
        Returns:
            list: A list of City objects belonging to the specified country,
                  sorted alphabetically by name. Empty list if country not found.
                  Note: this can be a large dataset for some countries.
        """
        if not country_code:
            return []
            
        cities = City.get_cities()
        country_cities = [city for city in cities if city.country_code == country_code]
        return sorted(country_cities, key=lambda x: x.name)