import streamlit as st

st.title("Electrical :blue[drawing]")
# st.write("Hello World")

option = st.selectbox(
    "Please select language",
    ("Hindi", "English","Spanish"),
)

st.write("You selected:", option)

st.text_area(
    "Output",
    "It was the best of times, it was the worst of times, it was the age of "
    "wisdom, it was the age of foolishness, it was the epoch of belief, it "
    "was the epoch of incredulity, it was the season of Light, it was the "
    "season of Darkness, it was the spring of hope, it was the winter of "
    "despair, (...)",
)