'use strict';
const assert = require('node:assert/strict');
const {after, before, describe, it} = require('node:test');
const { faker } = require('@faker-js/faker');
const {
    setPerson, getPersons, getPerson, deletePersons,
} = require('../data/index');
const {getConnection, closeConnection} = require('../data/connection');

describe('Data Tests', () => {
    before(async () => {
        await deletePersons();
    });
    after(async () => {
        await deletePersons();
        await closeConnection();
    });
    it('Can connect to DB', {timeout: 5000}, async () => {
        const connection = await getConnection();
        assert.equal(typeof connection, 'object');
        await closeConnection();
    });

    it('Can create Person to DB', {timeout: 5000}, async () => {
        const firstName = faker.name.firstName();
        const lastName = faker.name.firstName();

        await setPerson({firstName,lastName});
        const persons = await getPersons();
        assert.ok(Array.isArray(persons));
        const person = await getPerson(persons[0].id.toString());
        assert.equal(typeof person, 'object');
        assert.equal(person.id, persons[0].id.toString());
    });
});
