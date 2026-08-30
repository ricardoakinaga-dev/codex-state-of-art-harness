CREATE TRIGGER appointments_actor_client_match_insert
BEFORE INSERT ON appointments
WHEN NOT EXISTS (
    SELECT 1 FROM actors
    WHERE actors.id = NEW.actor_id AND actors.client_id = NEW.client_id
)
BEGIN
    SELECT RAISE(ABORT, 'appointment actor/client ownership mismatch');
END;

CREATE TRIGGER appointments_actor_client_match_update
BEFORE UPDATE OF actor_id, client_id ON appointments
WHEN NOT EXISTS (
    SELECT 1 FROM actors
    WHERE actors.id = NEW.actor_id AND actors.client_id = NEW.client_id
)
BEGIN
    SELECT RAISE(ABORT, 'appointment actor/client ownership mismatch');
END;

CREATE TRIGGER appointments_patient_client_match_insert
BEFORE INSERT ON appointments
WHEN NOT EXISTS (
    SELECT 1 FROM patients
    WHERE patients.id = NEW.patient_id AND patients.client_id = NEW.client_id
)
BEGIN
    SELECT RAISE(ABORT, 'appointment patient/client ownership mismatch');
END;

CREATE TRIGGER appointments_patient_client_match_update
BEFORE UPDATE OF patient_id, client_id ON appointments
WHEN NOT EXISTS (
    SELECT 1 FROM patients
    WHERE patients.id = NEW.patient_id AND patients.client_id = NEW.client_id
)
BEGIN
    SELECT RAISE(ABORT, 'appointment patient/client ownership mismatch');
END;

CREATE TRIGGER actors_client_reassignment_guard
BEFORE UPDATE OF client_id ON actors
WHEN EXISTS (
    SELECT 1 FROM appointments
    WHERE appointments.actor_id = OLD.id
      AND appointments.client_id <> NEW.client_id
)
BEGIN
    SELECT RAISE(ABORT, 'actor client ownership cannot be reassigned');
END;

CREATE TRIGGER patients_client_reassignment_guard
BEFORE UPDATE OF client_id ON patients
WHEN EXISTS (
    SELECT 1 FROM appointments
    WHERE appointments.patient_id = OLD.id
      AND appointments.client_id <> NEW.client_id
)
BEGIN
    SELECT RAISE(ABORT, 'patient client ownership cannot be reassigned');
END;
