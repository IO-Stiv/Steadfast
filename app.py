from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from threading import Lock
import os
import random

app = Flask(__name__)

# Set the secret key to some random bytes. Keep this really secret!
app.secret_key = os.urandom(24)

# Configure the SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///participants.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database
db = SQLAlchemy(app)


# Define a model for participants
class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(50), nullable=True)


class HistoricalTeam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_number = db.Column(db.Integer, nullable=False)
    participant_id = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(50), nullable=False)


with app.app_context():
    db.create_all()


# Custom Admin Index View
class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        # Fetch the list of teams and their participants
        teams_data = []
        for team in teams:
            team_data = [{'participant_id': p.participant_id, 'role': p.role} for p in team]
            teams_data.append(team_data)
        return self.render('admin_index.html', teams=teams_data)


# Admin view for historical teams
class HistoricalTeamsView(BaseView):
    @expose('/')
    def index(self):
        historical_teams = db.session.query(HistoricalTeam.team_number, HistoricalTeam.participant_id,
                                            HistoricalTeam.role).all()
        return self.render('admin/historical_teams.html', historical_teams=historical_teams)


# Initialize the Admin interface
admin = Admin(app, name='Admin', template_mode='bootstrap3', index_view=MyAdminIndexView())
admin.add_view(ModelView(Participant, db.session))
admin.add_view(HistoricalTeamsView(name='Historical Teams', endpoint='historical_teams'))

# This will hold the participants' queue and teams
participants_queue = []
teams = []
queue_lock = Lock()

# Roles to be assigned
roles = ['Cypher', 'Vanguard', 'Communicator']


# Endpoint to serve the HTML page
@app.route('/')
def index():
    return render_template('index.html')


# Endpoint for participants to join the queue
@app.route('/join', methods=['POST'])
def join_queue():
    participant_id = request.json.get('participant_id')
    if not participant_id:
        return jsonify("Participant ID is required"), 400

    with queue_lock:
        # Save the participant to the database
        new_participant = Participant(participant_id=participant_id)
        db.session.add(new_participant)
        db.session.commit()

        participants_queue.append(new_participant)

        # Check if there are 3 participants
        if len(participants_queue) >= 3:
            group = participants_queue[:3]
            participants_queue[:] = participants_queue[3:]

            roles = ['Cypher', 'Vanguard', 'Communicator']
            random.shuffle(roles)

            # Assign roles to each participant in the group
            team_number = len(teams) + 1
            for i, participant in enumerate(group):
                participant.role = roles[i]
                db.session.add(participant)  # Add participant back to session to update role

                # Save the team to historical data
                historical_team_entry = HistoricalTeam(
                    team_number=team_number,
                    participant_id=participant.participant_id,
                    role=participant.role
                )
                db.session.add(historical_team_entry)

            db.session.commit()  # Commit all role changes and historical data at once

            teams.append(group)
            group_message = f"Welcome Team ({', '.join([f'{p.participant_id} as {p.role}' for p in group])}). Please enter Zoom room xxx-xxx to join the experiment. Make sure you will use your prolific ID as your nick name."
            return jsonify(group_message), 200
        else:
            return jsonify("Waiting for more participants"), 200


# Endpoint to check the queue status
@app.route('/status', methods=['GET'])
def check_status():
    with queue_lock:
        return jsonify({
            "current_count": len(participants_queue),
            "queue": [p.participant_id for p in participants_queue],
            "teams": [[{'name': p.participant_id, 'role': p.role} for p in team] for team in teams]
        }), 200


# Endpoint to get all participants
@app.route('/participants', methods=['GET'])
def get_participants():
    participants = Participant.query.all()
    participant_list = [{'id': p.id, 'participant_id': p.participant_id, 'role': p.role} for p in participants]
    return jsonify(participant_list), 200


# Endpoint to update a participant
@app.route('/participants/<int:id>', methods=['PUT'])
def update_participant(id):
    data = request.json
    participant = Participant.query.get(id)
    if not participant:
        return jsonify("Participant not found"), 404

    participant.participant_id = data.get('participant_id', participant.participant_id)
    participant.role = data.get('role', participant.role)
    db.session.commit()
    return jsonify("Participant updated"), 200


# Endpoint to delete a participant
@app.route('/participants/<int:id>', methods=['DELETE'])
def delete_participant(id):
    participant = Participant.query.get(id)
    if not participant:
        return jsonify("Participant not found"), 404

    db.session.delete(participant)
    db.session.commit()
    return jsonify("Participant deleted"), 200


# Route for refreshing (clearing) teams
@app.route('/admin/refresh_teams', methods=['GET'])
def refresh_teams():
    global teams
    with queue_lock:
        # Clear the teams list
        teams.clear()

        # Optionally, remove roles from participants in the database
        participants = Participant.query.all()
        for participant in participants:
            participant.role = None
        db.session.commit()

    return jsonify({"status": "success"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=True)
