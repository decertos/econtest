from waitress import serve
import app


# USE THIS IF YOU WANT TO RUN WSGI
serve(app.app, host="0.0.0.0", port=5000)